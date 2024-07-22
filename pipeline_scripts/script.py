import os
import yaml
import snowflake.connector
import git

def get_changed_files(schema_folder):
  repo = git.Repo()
  previous_commit = repo.commit('HEAD~1')
  current_commit = repo.commit('HEAD')
  diff = current_commit.diff(previous_commit)

  changed_sql_files = []
  for d in diff:
    if d.a_path.startswith(schema_folder) and d.a_path.endswith('.sql'):
      changed_sql_files.append(d.a_path)

  return changed_sql_files

def execute_sql_scripts(changed_files, schema_folder):
  # Get Snowflake connection details from environment variables
  ctx = snowflake.connector.connect(
      user='<user>',
      password='<password>',
      account='<account>',
      warehouse='<warehouse>',
      database='<database>',
      schema='<schema>'
  )

  for sql_file in changed_files:
    with open(sql_file, 'r') as f:
      sql_code = f.read()

    with ctx.cursor() as cur:
      cur.execute(sql_code)
      ctx.commit()

def main():
  base_folders = ['CZ', 'RZ']  # Replace with your base folders

  for base_folder in base_folders:
    schema_folders = [os.path.join(base_folder, schema) for schema in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, schema))]

    for schema_folder in schema_folders:
      changed_files = get_changed_sql_files(schema_folder)
      if changed_files:
        execute_sql_scripts(changed_files, schema_folder)

if __name__ == "__main__":
  main()
