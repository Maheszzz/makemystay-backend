import subprocess
import sys
import os

def run_cmd(cmd, cwd=None):
    try:
        print(f"Running: {cmd}")
        # Use shell=True for complex commands, check=True to raise exception on failure
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=True, 
            text=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Stdout: {e.stdout}") # Typo in original fix
        print(f"Stderr: {e.stderr}")
        return None

def merge_mahes_to_main(repo_path):
    print(f"\n🚀 Processing Repository: {repo_path}")
    
    if not os.path.exists(repo_path):
        print(f"❌ Path does not exist: {repo_path}")
        return

    # Check current branch
    branch = run_cmd("git rev-parse --abbrev-ref HEAD", cwd=repo_path)
    if not branch: return

    print(f"   Current branch: {branch}")
    
    target_branch = "mahes"
    
    # If currently on mahes, we are good to merge FROM it. If on main, also fine.
    # But usually we want to merge mahes INTO main.
    
    # Strategy:
    # 1. Ensure we have the latest mahes locally. If we are on mahes, pull.
    # 2. Checkout main.
    # 3. Pull main.
    # 4. Merge mahes.
    # 5. Push main.
    # 6. Return to previous branch (or mahes).

    # First, handle uncommitted changes
    status = run_cmd("git status --porcelain", cwd=repo_path)
    if status:
        print("   📝 Found uncommitted changes. Committing...")
        run_cmd("git add .", cwd=repo_path)
        run_cmd('git commit -m "feat: save work before merge to main"', cwd=repo_path)
    else:
        print("   ✅ Clean working directory.")

    # 1. Update mahes
    if branch == "main":
        print(f"   ⬇️ Updating local '{target_branch}'...")
        run_cmd(f"git fetch origin {target_branch}:{target_branch}", cwd=repo_path) 
        # Above fetches remote mahes to local mahes (if fast forward)
    else:
        # Assuming we are on mahes or other feature branch
        if branch == target_branch:
             print(f"   ⬇️ Pulling latest '{target_branch}'...")
             run_cmd(f"git pull origin {target_branch}", cwd=repo_path)

    # 2. Checkout main
    if branch != "main":
        print("   twisted_rightwards_arrows Switching to 'main'...")
        res = run_cmd("git checkout main", cwd=repo_path)
        if res is None: return

    # 3. Pull main
    print("   ⬇️ Pulling latest 'main'...")
    run_cmd("git pull origin main", cwd=repo_path)

    # 4. Merge mahes
    print(f"   🔀 Merging '{target_branch}' into 'main'...")
    merge_res = run_cmd(f"git merge {target_branch}", cwd=repo_path)
    
    if merge_res is None:
        print("   ❌ Merge FAILED. Resolution required.")
        return

    # 5. Push main
    print("   ⬆️ Pushing 'main' to remote...")
    push_res = run_cmd("git push origin main", cwd=repo_path)
    
    if push_res is not None:
        print("   ✅ Successfully pushed 'main'.")
    else:
        print("   ❌ Push FAILED.")

    # 6. Switch back if we started on mahes
    if branch == target_branch:
        print(f"   back Switch back to '{target_branch}'...")
        run_cmd(f"git checkout {target_branch}", cwd=repo_path)
    
    print("   ✨ Done.")

if __name__ == "__main__":
    repos = [
        "/Users/maheswaranm/no-broker-backend",
        "/Users/maheswaranm/make-my-stay"
    ]
    for repo in repos:
        merge_mahes_to_main(repo)
