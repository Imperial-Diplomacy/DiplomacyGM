# Migration from 1.2.1 to 1.3.0
# 11-RenamedVariants.sql


to_rename = [
    ["helladip.json", "helladip.0.2"],
    ["impdip.json", "impdip.1.0"],
    ["impdip1.1.json", "impdip.1.1"],
    ["impdip_a1.json", "impdip.0.1"],
    ["impdipchaos.json", "impdip.1.4.chaos"],
    ["impdipchaos_sa.json", "impdip.1.2.chaos.sa"],
    ["impdipfow.json", "impdip.1.2.fow"],
    ["maddip.json", "maddip.0.2"],
    ["peloponnesian_war.json", "pelopondip.2.2"],
    ["impdip.1.2.json", "impdip.1.2"],
    ["impdip.1.4.json", "impdip.1.4"],
    ["impdip.1.5.json", "impdip.1.5"],
    ["impdip.2.0.json", "impdip.2.0"],
    ["impdip.1.6.json", "impdip.1.6"],
    ["helladip.0.3.json", "helladip.0.3"]
]

db_usages = [
    ["boards", "data_file"],
]

SQL_txt = "BEGIN TRANSACTION;"

SQL_format = """
UPDATE {table_name}
SET {column_name} = '{replace}'
WHERE {column_name} = '{search}';
"""

for table, column in db_usages:
    for find, replace in to_rename:
        SQL_txt += SQL_format.format(table_name=table, column_name=column, replace=replace, search=find)

SQL_txt += "\nCOMMIT;\n"

with open("11-RenamedVariants.sql", 'w') as f:
    f.write(SQL_txt)