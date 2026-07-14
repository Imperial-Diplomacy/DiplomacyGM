from DiploGM.models.substitute import SubstituteEvent, SubstituteType
from DiploGM.repositories.substitute import substitute_repo
from DiploGM.services.base import BaseService

class SubstituteService(BaseService):
    def __init__(self) -> None:
        self.repo = substitute_repo

    def create_sub(self, 
                   server_id: int, 
                   user_id: int, 
                   power: str, 
                   sub_type: SubstituteType
    ):
        if sub_type not in [
            SubstituteType.INCOMING, 
            SubstituteType.OUTGOING
        ]:
            raise ValueError("Trying to log a substitute that isn't permanent.")

        if not self.verify_same_power(server_id, user_id, power):
            raise ValueError("User has previously been logged for another power.")

        event = SubstituteEvent(
            server_id=server_id,
            power=power,
            user_id=user_id,
            sub_type=sub_type
        )

        self.repo.save(event)
        
    def create_temp_sub(self,
                        server_id: int, 
                        user_id: int, 
                        power: str, 
                        sub_type: SubstituteType,
                        days: int
    ):
        if sub_type not in [
            SubstituteType.TEMP_INCOMING, 
            SubstituteType.TEMP_OUTGOING
        ]:
            raise ValueError("Trying to log a substitute that isn't temporary.")

        if not self.verify_same_power(server_id, user_id, power):
            raise ValueError("User has previously been logged for another power.")

        event = SubstituteEvent(
            server_id=server_id,
            power=power,
            user_id=user_id,
            sub_type=sub_type,
            days=days,
        )

        self.repo.save(event)

    def verify_same_power(self, server_id: int, user_id: int, power: str) -> bool:
        subs = self.get_server_user_subs(server_id, user_id)
        if len(subs) == 0:
            return True

        return all(map(lambda e: e.power == power, subs))

    def get_server_user_subs(self, server_id: int, user_id: int) -> list[SubstituteEvent]:
        return list(self.repo.find_by(
            lambda e: e.server_id == server_id and e.user_id == user_id
        ))

    def get_server_subs(self, server_id: int) -> list[SubstituteEvent]:
        return list(self.repo.find_by(
            lambda e: e.server_id == server_id
        ))

    def get_user_subs(self, user_id: int) -> list[SubstituteEvent]:
        return list(self.repo.find_by(
            lambda e: e.user_id == user_id
        ))

substitute_service = SubstituteService()
