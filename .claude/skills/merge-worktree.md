---
name: merge-worktree
description: Merge the current worktree branch into master
user_invocable: true
---

# Merge Worktree

Merge the current worktree branch into the main repository's master branch.

## Steps

1. Get the current branch name: `git rev-parse --abbrev-ref HEAD`
2. Get the main repo path by finding the parent of `.claude/worktrees/`: `git rev-parse --path-format=absolute --git-common-dir` then strip the `/.git` suffix
3. Merge using: `git -C <main_repo_path> merge <branch_name>`
4. Report the result to the user

## Rules

- If there are uncommitted changes in the worktree, warn the user and stop
- If the merge has conflicts, report them and stop
- Do NOT push to remote unless explicitly asked
