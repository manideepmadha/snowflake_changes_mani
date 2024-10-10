import os
import yaml
from collections import defaultdict
import snowflake.connector
import sys
import json

def get_connection():
    """
    Establishes and returns a Snowflake database connection using environment variables.
    """
    user = os.getenv('SNOWFLAKE_USERNAME')
    password = os.getenv('SNOWFLAKE_PASSWORD')
    account = os.getenv('SNOWFLAKE_ACCOUNT')
    warehouse = os.getenv('SNOWFLAKE_WAREHOUSE')

    return snowflake.connector.connect(
        user=user,
        password=password,
        account=account,
        warehouse=warehouse,
        role="ACCOUNTADMIN"
    )
def execute_sql_function(folder, files):
    print(f"\nHello! Executing SQL function for folder '{folder}' with the following files:")
    for i, sql_file in enumerate(files, 1):
        if sql_file.endswith(':changes.yml'):
            print(f"\tSkipping file: {sql_file} (Not an SQL file)")
            continue

        if sql_file.lower().endswith('.sql'):
            print(f"\t{i}. {sql_file}")
            try:
                with open(sql_file, 'r') as file:
                    sql_query = file.read()
            except Exception as e:
                print(f"\tERROR: Unable to read file {sql_file}: {e}")
                sys.exit(1)

            # Execute the SQL query
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    print(f"\t\tExecuting SQL file: {sql_file}")
                    cursor.execute(sql_query)
                    print("\t\tSQL file executed successfully.")
            except Exception as e:
                print(f"\t\tERROR: SQL execution failed: {e}")
                sys.exit(1)
            finally:
                conn.close()
        else:
            print(f"\tSkipping file: {sql_file} (Not an SQL file)")
    


def validate_changes_yml(changes_yml_path, file_list):
    print("\n\tProcess started for validating changes.yml file\n")

    files_in_changes_yml = []
    files_not_in_changes_yml = []

    try:
        with open(changes_yml_path, 'r') as file:
            changes_data = yaml.safe_load(file)
            
        # Extract file paths from changes.yml
        yml_files = [change['file_path'] for change in changes_data.get('changes', [])]
        
        # Check each file in the folder (except changes.yml) against changes.yml
        for file in file_list:
            if file.endswith("changes.yml"):
                continue
            # Remove the leading "./" from file paths to match with paths in changes.yml
            relative_path = file.lstrip("./")
            
            if relative_path in yml_files:
                files_in_changes_yml.append(relative_path)
            else:
                files_not_in_changes_yml.append(relative_path)
    
    except Exception as e:
        print(f"\t\tERROR: Unable to read or parse {changes_yml_path}: {e}")
        sys.exit(1)

    # Print the summary
    print("\n\tValidation Summary:\n")
    
    if files_in_changes_yml:
        print("\t\tFiles listed in changes.yml:")
        for i, file in enumerate(files_in_changes_yml, 1):
            print(f"\t\t\t{i}. {file}")
    else:
        print("\t\tNo files are listed in changes.yml.")

    if files_not_in_changes_yml:
        print("\n\tFiles NOT listed in changes.yml:")
        for i, file in enumerate(files_not_in_changes_yml, 1):
            print(f"\t\t\t{i}. {file}")
        return False
    else:
        print("\t\tAll files are listed in changes.yml.")
        return True

def process_added_files(added_files):
    print("Added File List:")
    if added_files:
        print(f"{added_files}")
        file_list = added_files.split()
        folder_files = defaultdict(list)
        
        all_folders_valid = True
        folder_files_for_sql = {}

        for file in file_list:
            folder_name = file.split('/')[1]
            folder_files[folder_name].append(file)
        
        for folder, files in folder_files.items():
            folder_files_for_sql[folder] = files
            execute_sql_function(folder, files)
            
        #     if folder != ".github":
        #         print(f"\n{folder} Folder Processing:")
                    
                
        #         changes_yml_exists = any(file.endswith("changes.yml") for file in files)

        #         if changes_yml_exists:
        #             print(f"\tValid Folder '{folder}' because it contains: changes.yml")
        #             print(f"\t  Files added in '{folder}':")
        #             for i, file in enumerate(files, 1):
        #                 relative_path = file.lstrip("./")
        #                 print(f"\t\t{i}. {relative_path}")
        #             changes_yml_path = next(file for file in files if file.endswith("changes.yml"))
        #             if validate_changes_yml(changes_yml_path, files):
        #                 folder_files_for_sql[folder] = files
        #             else:
        #                 all_folders_valid = False
        #         else:
        #             print(f"\tInvalid Folder '{folder}' due to missing: changes.yml")
        #             for i, file in enumerate(files, 1):
        #                 relative_path = file.lstrip("./")
        #                 print(f"\t\t{i}. {relative_path}")
        #             all_folders_valid = False
        #     else:
        #         print(f"\n Skipping unsupported folder: '{folder}'. Only folders 'DEV', 'QA', or 'PROD' are processed.\n")

        # if all_folders_valid:
        #     # All folders have successfully validated their files against changes.yml
        #     for folder, files in folder_files_for_sql.items():
        #         execute_sql_function(folder, files)
        # else:
        #     print("All folder are not valid so not able to execute sql files")
        #     sys.exit(1)
    else:
        print("\nNo files were added or environment variable is not set.")

def main():
    added_files = os.getenv('ADDED_FILES')
    data_list = json.loads(added_files)

    result = ' '.join(f'./{item}' for item in data_list)
    
    process_added_files(result)

if __name__ == "__main__":
    main()
