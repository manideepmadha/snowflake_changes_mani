#!/bin/bash

# Arguments
folder="$1"          # Folder to filter files from
file_extension="$2"  # File extension to filter, e.g., .json
log_count="$3"       # Number of logs to consider

# Retrieve the latest merge commits
latest_commits=$(git log origin/main --merges -n "$log_count" --pretty=format:%H)

# Check if any merge commits were found
if [ -z "$latest_commits" ]; then
  echo "No merge commits found."
  exit 1
fi


# Use an associative array to collect unique changed files
declare -A file_set


for commit in $latest_commits; do
  files=$(git diff-tree --no-commit-id --name-status -r "$commit" | awk '$1 != "D" {print $NF}')
  changed_files+=$'\n'"$files"
done

# Loop through each merge commit
for commit in $merge_commits; do
  echo "Processing merge commit: $commit"

  # Get the two parent commits of the merge
  parents=$(git rev-list --parents -n 1 $commit)

  # Extract only the parent commit IDs (ignoring the merge commit itself)
  parent1=$(echo $parents | awk '{print $2}')
  parent2=$(echo $parents | awk '{print $3}')

  # Perform a diff between the two parents to get changed files
  commit_files=$(git diff --name-status $parent1 $parent2 | awk '$1 != "D" {print $NF}')

  # Add the files to the associative array
  for file in $commit_files; do
    file_set["$file"]=1
  done
done

# Extract unique files from the array
unique_files=$(printf "%s\n" "${!file_set[@]}")


# Filter unique files from the specified folder with the given extension
filtered_files=$(echo "$unique_files" | grep "$folder" | grep "$file_extension" | sort -u || true)

echo $filtered_files



