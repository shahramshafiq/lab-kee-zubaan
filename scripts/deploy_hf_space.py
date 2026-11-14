"""Creates the Hugging Face Space, sets its secrets, and uploads the app. Run it yourself in a terminal:

    powershell -File scripts\prepare_hf_space.ps1     (first: builds the clean upload folder C:\dev\hf-space)
    python scripts\deploy_hf_space.py

You type three things at hidden prompts: your Hugging Face token (write access) and your two AI keys. Nothing is saved
by this script, and the keys go straight to the Space's secret settings (not into any file).
Use --dry-run to check everything except the upload.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

FOLDER = Path(r"C:\dev\hf-space")
SPACE_NAME = "lab-kee-zubaan"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="check the folder and the library, then stop")
    ap.add_argument("--folder", default=str(FOLDER))
    ap.add_argument("--name", default=SPACE_NAME)
    args = ap.parse_args()

    folder = Path(args.folder)
    needed = ["Dockerfile", "README.md", "requirements.txt", "app", "static", "lab_reports"]
    missing = [n for n in needed if not (folder / n).exists()]
    if missing:
        sys.exit(f"The upload folder is not ready ({missing}). Run: powershell -File scripts\\prepare_hf_space.ps1")
    if any((folder / n).exists() for n in (".env", ".env.example")):
        sys.exit("A .env file is in the upload folder. Remove it first.")
    try:
        from huggingface_hub import HfApi
    except ImportError:
        sys.exit("Install the library first: pip install huggingface_hub")
    print(f"Upload folder OK: {folder}")
    if args.dry_run:
        print("Dry run finished. Nothing was sent.")
        return

    token = os.getenv("HF_TOKEN") or getpass.getpass("Hugging Face token (write access, typing is hidden): ").strip()
    api = HfApi(token=token)
    try:
        user = api.whoami()["name"]
    except Exception:
        sys.exit("That token was not accepted. Create a token with WRITE access and try again.")
    repo_id = f"{user}/{args.name}"
    print(f"Signed in as {user}. Space: {repo_id}")

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    for secret in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        value = getpass.getpass(f"{secret} (typing is hidden, press Enter to skip): ").strip()
        if value:
            api.add_space_secret(repo_id, secret, value)
    api.add_space_variable(repo_id, "PROVIDER_ORDER", "groq,gemini")
    api.add_space_variable(repo_id, "LLM_MAX_CALLS_PER_HOUR", "1500")

    print("Uploading the app...")
    api.upload_folder(folder_path=str(folder), repo_id=repo_id, repo_type="space",
                      commit_message="first upload of the app")
    print("\nDone. The build starts now and takes a few minutes.")
    print(f"Space page: https://huggingface.co/spaces/{repo_id}")
    print(f"Live link:  https://{user.lower()}-{args.name}.hf.space")


if __name__ == "__main__":
    main()
