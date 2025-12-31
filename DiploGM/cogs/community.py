import datetime
import hashlib
import io
import logging
import matplotlib.pyplot as plt
import networkx as nx
import random
from sqlite3 import IntegrityError
from typing import Optional, Union

import discord
from discord.ext import commands

from DiploGM.config import ERROR_COLOUR
from DiploGM.perms import gm_only, is_superuser, superuser_only
from DiploGM.models.community.community import Community, SQLiteCommunityRepository
from DiploGM.models.community.relationship import (
    Relationship,
    RelationshipType,
    SQLiteRelationshipRepository,
)
from DiploGM.models.community.server import SQLiteServerRepository, Server
from DiploGM.utils.send_message import send_message_and_file

logger = logging.getLogger(__name__)


class CommunityService:
    def __init__(self) -> None:
        self.community_repo = SQLiteCommunityRepository()
        self.server_repo = SQLiteServerRepository()
        self.relation_repo = SQLiteRelationshipRepository()

    def create_community(self, name: str, owner: discord.User):
        cid = string_to_u32(name)
        c = Community(id=cid, name=name, description="")

        try:
            self.community_repo.save(c)
        except IntegrityError:
            pass

        rel = Relationship(owner.id, cid, RelationshipType.COMMUNITY_OWNER)
        self.relation_repo.save(rel)
        rel = Relationship(owner.id, cid, RelationshipType.COMMUNITY_MEMBER)
        self.relation_repo.save(rel)

    def delete_community(self, community: Community):
        self.community_repo.delete(community.id)
        relations = [
            r.id
            for r in self.relation_repo.find_by(lambda r: r.object_id == community.id)
            if r.id is not None
        ]
        self.relation_repo.delete_many(relations)

    def get_community(self, identifier: Union[int, str]) -> Optional[Community]:
        if isinstance(identifier, int):
            return self.community_repo.find_one_by(lambda c: c.id == identifier)

        if isinstance(identifier, str):
            return self.community_repo.find_one_by(lambda c: c.name == identifier)

    def is_community_owner(self, community: Community, user: discord.User) -> bool:
        rel = self.relation_repo.find_one_by(
            lambda r: r.subject_id == user.id
            and r.object_id == community.id
            and r.type == RelationshipType.COMMUNITY_OWNER
        )
        if rel:
            return True

        return False

    def is_user_in_community(self, community: Community, user: discord.User) -> bool:
        rel = self.relation_repo.find_one_by(
            lambda r: r.subject_id == user.id
            and r.object_id == community.id
            and r.type == RelationshipType.COMMUNITY_MEMBER
        )
        if rel:
            return True

        return False

    def is_server_in_community(self, server_id: int) -> Optional[int]:
        rel = self.relation_repo.find_one_by(
            lambda r: r.subject_id == server_id
            and r.type == RelationshipType.COMMUNITY_SERVER
        )
        if rel:
            return rel.object_id

        return None

    def register_server_to_community(self, community: Community, server_id: int):
        rel = Relationship(server_id, community.id, RelationshipType.COMMUNITY_SERVER)
        self.relation_repo.save(rel)

    def unregister_server_to_community(self, community: Community, server_id: int):
        rel = self.relation_repo.find_one_by(
            lambda r: r.subject_id == server_id
            and r.object_id == community.id
            and r.type == RelationshipType.COMMUNITY_SERVER
        )
        if rel and rel.id:
            self.relation_repo.delete(rel.id)

    def take_registration_server(self, guild: discord.Guild):
        server = Server(guild.id, guild.name)
        self.server_repo.save(server)

        current_member_ids = {member.id for member in guild.members}

        existing_rels = self.relation_repo.find_by(
            lambda rel: rel.object_id == guild.id
            and rel.type == RelationshipType.SERVER_MEMBER
        )
        existing_member_ids = {rel.subject_id for rel in existing_rels}

        attending = [
            Relationship(
                subject_id=member_id,
                object_id=guild.id,
                type=RelationshipType.SERVER_MEMBER,
            )
            for member_id in current_member_ids - existing_member_ids
        ]
        self.relation_repo.save_many(attending)

        for rel in filter(
            lambda r: r.subject_id not in current_member_ids, existing_rels
        ):
            if rel.id:
                self.relation_repo.delete(rel.id)

    def register_user_to_community(self, community: Community, user_id: int):
        rel = Relationship(user_id, community.id, RelationshipType.COMMUNITY_MEMBER)
        self.relation_repo.save(rel)

    def unregister_user_to_community(self, community: Community, user_id: int):
        rel = self.relation_repo.find_one_by(
            lambda r: r.subject_id == user_id
            and r.object_id == community.id
            and r.type == RelationshipType.COMMUNITY_MEMBER
        )
        if rel and rel.id:
            self.relation_repo.delete(rel.id)


class CommunityCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.service = CommunityService()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.service.take_registration_server(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        rel = Relationship(member.id, member.guild.id, RelationshipType.SERVER_MEMBER)
        self.service.relation_repo.save(rel)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        rels = self.service.relation_repo.find_by(
            lambda r: r.subject_id == member.id and r.object_id == member.guild.id
        )
        for r in rels:
            if r.id:
                self.service.relation_repo.delete(r.id)

    @commands.group(name="community", brief="Entry point for community commands")
    async def community(self, ctx: commands.Context):
        await send_message_and_file(
            channel=ctx.channel,
            message="Valid commands are: *create/delete*, *register_server/unregister_server*, and *join/leave*",
        )

    @community.command(
        name="create",
        brief="Create a DiploGM community",
    )
    async def community_create(self, ctx: commands.Context, *, name: str):
        if name.isnumeric():
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message="Please don't use a numeric community name",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.create_community(name, ctx.author)
        await send_message_and_file(
            channel=ctx.channel,
            title="Community created!",
            message=f"You are now the owner of {name}",
        )

    @community.command(
        name="delete",
        brief="Delete a DiploGM community",
    )
    async def community_delete(self, ctx: commands.Context, *, community_id):
        if community_id.isnumeric():
            community_id = int(community_id)

        community = self.service.get_community(community_id)
        if community is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        if not self.service.is_community_owner(
            community, ctx.author
        ) and not is_superuser(ctx.author):
            await send_message_and_file(
                channel=ctx.channel,
                title="Bad Permissions!",
                message="You do not have permission to do that.",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.delete_community(community)
        await send_message_and_file(
            channel=ctx.channel,
            title="Community deleted!",
            message=f"'{community.name}' is no more.",
        )

    @community.command(
        name="list",
        brief="List all DiploGM communities",
    )
    async def community_list(self, ctx: commands.Context):
        out = ""
        communities = list(self.service.community_repo.all())

        for c in sorted(communities, key=lambda c: c.name):
            owner_rel = self.service.relation_repo.find_one_by(
                lambda r: r.object_id == c.id
                and r.type == RelationshipType.COMMUNITY_OWNER
            )
            if owner_rel and (owner := self.bot.get_user(owner_rel.subject_id)):
                out += f"({c.id}) {c.name} by {owner.mention}\n"
            else:
                out += f"({c.id}) {c.name} is untracked\n"

        await send_message_and_file(
            channel=ctx.channel, title="DiploGM Communities", message=out
        )

    @community.command(name="inspect", brief="Get some information about a community")
    async def community_inspect(self, ctx: commands.Context, *, community_id):
        assert ctx.guild is not None

        if community_id.isnumeric():
            community_id = int(community_id)

        community = self.service.get_community(community_id)
        if community is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        out = f"ID: {community.id}\n"
        owner_rel = self.service.relation_repo.find_one_by(
            lambda r: r.object_id == community.id
            and r.type == RelationshipType.COMMUNITY_OWNER
        )
        if owner_rel:
            user = self.bot.get_user(owner_rel.subject_id)
            out += f"Owner: {user.mention}\n"
        else:
            out += "Owner: *Unknown*\n"

        server_rels = list(
            self.service.relation_repo.find_by(
                lambda r: r.object_id == community.id
                and r.type == RelationshipType.COMMUNITY_SERVER
            )
        )
        out += f"Servers: {len(server_rels)}\n"
        if len(server_rels) > 0:
            for id in list(
                map(
                    lambda r: r.subject_id,
                    sorted(server_rels, key=lambda r: r.created_at, reverse=True),
                )
            )[:15]:
                server = self.service.server_repo.load(id)
                if server:
                    out += f"- {server.name}\n"

        member_rels = list(
            self.service.relation_repo.find_by(
                lambda r: r.object_id == community.id
                and r.type == RelationshipType.COMMUNITY_MEMBER
            )
        )
        out += f"Members: {len(member_rels)}\n"
        out += f"Registered at: {community.created_at}\n"

        await send_message_and_file(
            channel=ctx.channel, title=f"{community.name}", message=out
        )

    @community.command(
        name="register_server",
        brief="Register a server with a community",
    )
    @gm_only("register a community")
    async def community_register(self, ctx: commands.Context, *, community_id):
        assert ctx.guild is not None

        if community_id.isnumeric():
            community_id = int(community_id)

        community = self.service.get_community(community_id)
        if community is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        if self.service.is_server_in_community(ctx.guild.id) is not None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Community already registered!",
                message=f"The server is already registered under the '{community.name}' community.",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.register_server_to_community(community, ctx.guild.id)
        await send_message_and_file(
            channel=ctx.channel,
            title="Server registered!",
            message=f"{ctx.guild.name} is now registered to the '{community.name}' community.",
        )

    @community.command(
        name="unregister_server",
        brief="Unregister a server with a community",
    )
    @gm_only("register a community")
    async def community_unregister(self, ctx: commands.Context):
        assert ctx.guild is not None

        existing_community_id = self.service.is_server_in_community(ctx.guild.id)
        if existing_community_id is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Community not registered!",
                message="The server is not currently registered to any community.",
                embed_colour=ERROR_COLOUR,
            )
            return

        community = self.service.get_community(existing_community_id)
        if not community:
            raise ValueError(
                f"The community attached to this server '{existing_community_id}' could not be found, contact a Bot Superuser."
            )

        if not self.service.is_community_owner(
            community, ctx.author
        ) and not is_superuser(ctx.author):
            await send_message_and_file(
                channel=ctx.channel,
                title="Bad Permissions!",
                message="You do not have permission to do that.",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.unregister_server_to_community(community, ctx.guild.id)
        await send_message_and_file(
            channel=ctx.channel,
            title="Server unregistered!",
            message=f"{ctx.guild.name} is no longer registered to the '{community.name}' community.",
        )

    @community.command(
        name="join",
        brief="Join a community",
    )
    async def community_join(self, ctx: commands.Context, *, community_id):
        if community_id.isnumeric():
            community_id = int(community_id)

        community = self.service.get_community(community_id)
        if community is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        if self.service.is_user_in_community(community, ctx.author):
            await send_message_and_file(
                channel=ctx.channel,
                message="You're already in that community!",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.register_user_to_community(community, ctx.author.id)
        await send_message_and_file(
            channel=ctx.channel,
            message=f"You joined '{community_id}', hope you enjoy your stay!",
        )

    @community.command(
        name="leave",
        brief="Leave a community",
    )
    async def community_leave(self, ctx: commands.Context, *, community_id):
        if community_id.isnumeric():
            community_id = int(community_id)

        community = self.service.get_community(community_id)
        if community is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid name!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        if not self.service.is_user_in_community(community, ctx.author):
            await send_message_and_file(
                channel=ctx.channel,
                message="You're not in that community!",
                embed_colour=ERROR_COLOUR,
            )
            return

        if self.service.is_community_owner(community, ctx.author):
            await send_message_and_file(
                channel=ctx.channel,
                message="### You're the owner of that community!\nFind a replacement owner and contact a bot superuser to replace.",
                embed_colour=ERROR_COLOUR,
            )
            return

        self.service.unregister_user_to_community(community, ctx.author.id)
        await send_message_and_file(
            channel=ctx.channel,
            message=f"You left '{community_id}', wishing you well going forward!",
        )

    @community.command(name="graph", brief="create a DiploGM community network")
    @superuser_only("create a community graph")
    async def community_graph(self, ctx: commands.Context):
        G = nx.DiGraph()
        rels = self.service.relation_repo.find_by(
            lambda r: r.type
            in [
                RelationshipType.SERVER_MEMBER,
                RelationshipType.COMMUNITY_MEMBER,
                RelationshipType.COMMUNITY_SERVER,
            ]
        )

        for r in rels:
            if r.type == RelationshipType.SERVER_MEMBER:
                G.add_node(r.subject_id, type="user")

                server = self.service.server_repo.load(r.object_id)
                if server:
                    G.add_node(r.object_id, type="server", label=server.name)
                    G.add_edge(r.subject_id, r.object_id)

            if r.type == RelationshipType.COMMUNITY_MEMBER:
                G.add_node(r.subject_id, type="user")

                community = self.service.community_repo.load(r.object_id)
                if community:
                    G.add_node(r.object_id, type="community", label=community.name)
                    G.add_edge(r.subject_id, r.object_id)

            if r.type == RelationshipType.COMMUNITY_SERVER:
                server = self.service.server_repo.load(r.subject_id)
                community = self.service.community_repo.load(r.object_id)
                if server and community:
                    G.add_node(r.subject_id, type="server", label=server.name)
                    G.add_node(r.object_id, type="community", label=community.name)
                    G.add_edge(r.subject_id, r.object_id)

        plt.figure(figsize=(10, 10))

        def node_colors_by_type(G):
            colors = []
            for n in G.nodes:
                rnd = random.Random(n)  # deterministic per server id
                if G.nodes[n]["type"] == "server":
                    colors.append(
                        (
                            rnd.uniform(0.7, 1.0),  # R
                            rnd.uniform(0.6, 0.9),  # G
                            rnd.uniform(0.1, 0.4),  # B
                        )
                    )
                elif G.nodes[n]["type"] == "community":
                    colors.append(
                        (
                            rnd.uniform(0.3, 0.6),  # R
                            rnd.uniform(0.7, 1.0),  # G
                            rnd.uniform(0.2, 0.5),  # B
                        )
                    )
                else:
                    colors.append(
                        (
                            rnd.uniform(0.3, 0.6),  # R
                            rnd.uniform(0.2, 0.5),  # G
                            rnd.uniform(0.7, 1.0),  # B
                        )
                    )
            return colors

        def node_sizes_by_type(G):
            NODE_TYPE_SIZES = {
                "server": 700,
                "community": 1500,
                "user": 50,
            }

            G_rev = G.reverse(copy=False)
            node_sizes = []
            for n in G.nodes:
                type = G.nodes[n].get("type")
                if type is None:
                    continue

                size = 400
                if type == "server":
                    size = NODE_TYPE_SIZES.get(type, 3000) + (100 * len(G.in_edges(n)))
                if type == "community":
                    covered_nodes = set()
                    boost = 0
                    distances = nx.single_source_shortest_path_length(
                        G_rev, source=n, cutoff=3
                    )

                    for u, d in distances.items():
                        if u in covered_nodes:
                            continue

                        if d == 1:
                            boost += 250
                        if d == 2:
                            boost += 50

                    size = NODE_TYPE_SIZES.get(type, 2200) + boost

                node_sizes.append(size)

            return node_sizes

        def layered_layout(G):
            pos = {}

            communities = [n for n in G if G.nodes[n]["type"] == "community"]
            servers = [n for n in G if G.nodes[n]["type"] == "server"]
            users = [n for n in G if G.nodes[n]["type"] == "user"]

            # Communities in center
            pos.update(
                nx.circular_layout(G.subgraph(communities), center=(0, 0), scale=10.0)
            )

            # Servers around communities
            pos.update(
                nx.spring_layout(
                    G.subgraph(servers), scale=30.0, k=1.2, iterations=100, seed=42
                )
            )

            # Users pushed outward
            pos.update(
                nx.spring_layout(
                    G.subgraph(users), scale=100.0, k=1.5, iterations=250, seed=42
                )
            )

            return pos

        nx.draw(
            G,
            pos=layered_layout(G),
            with_labels=True,
            labels={n: G.nodes[n].get("label", "") for n in G.nodes},
            font_size=8,
            node_color=node_colors_by_type(G),
            node_size=node_sizes_by_type(G),
            edge_color="lightgray",
        )

        # Save to BytesIO
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        plt.close()

        await ctx.send(file=discord.File(buf, filename="graph.png"))

    @community.command(name="transfer", brief="Transfer ownership of a community")
    @superuser_only("transfer ownership")
    async def community_transfer(
        self, ctx: commands.Context, community_id: int, new_owner: discord.User
    ):
        if self.service.community_repo.load(community_id) is None:
            await send_message_and_file(
                channel=ctx.channel,
                title="Invalid ID!",
                message=f"The community '{community_id}' does not exist.",
                embed_colour=ERROR_COLOUR,
            )
            return

        curr_owner = self.service.relation_repo.find_one_by(
            lambda r: r.object_id == community_id
            and r.type == RelationshipType.COMMUNITY_OWNER
        )
        if curr_owner and curr_owner.id:
            self.service.relation_repo.delete(curr_owner.id)

        new_rel = Relationship(
            new_owner.id, community_id, RelationshipType.COMMUNITY_OWNER
        )
        self.service.relation_repo.save(new_rel)
        new_rel = Relationship(
            new_owner.id, community_id, RelationshipType.COMMUNITY_MEMBER
        )
        self.service.relation_repo.save(new_rel)

    @commands.command(name="me", brief="Get some information about you")
    async def me(self, ctx: commands.Context):
        out = (
            "### You\n"
            f"User ID: {ctx.author.id}\n"
            f"Username: {ctx.author.name}\n"
            f"Mention: {ctx.author.mention}\n"
        )

        comm_repo = self.service.community_repo
        serv_repo = self.service.server_repo
        rel_repo = self.service.relation_repo

        communities = list(
            rel_repo.find_by(
                lambda r: r.subject_id == ctx.author.id
                and r.type
                in [RelationshipType.COMMUNITY_MEMBER, RelationshipType.COMMUNITY_OWNER]
            )
        )
        if len(communities) != 0:
            processed_communties = set()
            out += "### Communities\n"
            for i, rel in enumerate(communities):
                if rel.object_id in processed_communties:
                    continue

                community = comm_repo.load(rel.object_id)
                if community is None:
                    continue

                out += f"- {community.name} {'(owner)' if self.service.is_community_owner(community, ctx.author) else ''}\n"
                processed_communties.add(rel.object_id)

        servers = list(
            rel_repo.find_by(
                lambda r: r.subject_id == ctx.author.id
                and r.type in [RelationshipType.SERVER_MEMBER]
            )
        )
        if len(servers) != 0:
            out += "### Servers\n"
            for i, rel in enumerate(servers):
                server = serv_repo.load(rel.object_id)
                if server is None:
                    continue

                out += f"- {server.name}\n"

        await send_message_and_file(channel=ctx.channel, message=out)

    @commands.command(brief="Populate community relationships for server.")
    @superuser_only("populate a server into the community graph")
    async def populate(self, ctx: commands.Context):
        assert ctx.guild is not None

        start = datetime.datetime.now()
        self.service.take_registration_server(ctx.guild)
        diff = datetime.datetime.now() - start

        await send_message_and_file(
            channel=ctx.channel,
            title="Populated server relationships!",
            message=f"Took: {diff}",
        )

    @commands.command(brief="Populate community relationships for DiploGM.")
    @superuser_only("populate all servers into the community graph")
    async def populate_all(self, ctx: commands.Context):
        assert ctx.guild is not None

        out = ""
        for guild in self.bot.guilds:
            start = datetime.datetime.now()
            self.service.take_registration_server(guild)
            diff = datetime.datetime.now() - start

            out += f"{guild.name} Took: {diff}\n"

        await send_message_and_file(
            channel=ctx.channel, title="Populated server relationships!", message=out
        )


def string_to_u32(s: str) -> int:
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()
    code = int(digest, 16) % (10**8)
    return code


async def setup(bot):
    cog = CommunityCog(bot)
    await bot.add_cog(cog)
