# Publish To GitHub

## 1) Create an empty GitHub repository

Create a new repo on GitHub, for example: `SideVoiceTray`.
Do not initialize it with README/LICENSE/.gitignore.

## 2) Push this local repository

```bash
cd C:\Projects\SideVoiceTray
git remote add origin https://github.com/<YOUR_USERNAME>/SideVoiceTray.git
git push -u origin main
```

## 3) Next updates

```bash
git add .
git commit -m "your message"
git push
```
