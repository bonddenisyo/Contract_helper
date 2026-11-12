# Deploy to Northflank

Result: a public link (like `https://web--contract-copilot--xxxx.code.run`) that anyone can open in a browser.

The repo already contains everything Northflank needs: a `Dockerfile`, a `.dockerignore`, and Streamlit settings in `.streamlit/config.toml`.

## Before you start

- **A GitHub account and repository.** Upload the whole `contract-copilot` folder to a new repository. A private repo is fine. Do **not** upload a `.env` file; the `.gitignore` already excludes it.
- **A free AI key**, ideally Cloudflare Workers AI (see the README).
- **Northflank:** the free Developer Sandbox allows 2 services, 2 jobs and 1 addon. Contract Copilot is added as the **second service in your existing project**, so it doesn't need a new project. It runs separately from your other service; they only share the project.

## Steps

1. **Connect GitHub.** In Northflank, open your account settings → Git integrations → link GitHub and give it access to the repository.
2. **Open your existing project.** Don't create a new one; the free plan allows only one.
3. **Create a service** inside that project. Choose *Combined service* (builds from Git and runs it). Name it `contract-copilot` so it's easy to tell apart from your other service.
   - Repository: your `contract-copilot` repo, branch `main`.
   - Build type: **Dockerfile**. Dockerfile location: `/Dockerfile`. Build context: `/`.
4. **Ports.** Add port **8080**, protocol **HTTP**, and turn on **Publicly expose**. Northflank gives you the public URL.
5. **Environment variables.** Add these as *runtime variables* (mark the keys as secret):

   | Variable | Value |
   |---|---|
   | `CLOUDFLARE_ACCOUNT_ID` | your Cloudflare account ID |
   | `CLOUDFLARE_API_TOKEN` | your Workers AI token |
   | `GEMINI_API_KEY` / `GROQ_API_KEY` | optional fallbacks |
   | `ADMIN_PASSWORD` | a long password; hides the audit log from visitors |
   | `DAILY_REVIEW_LIMIT` | e.g. `100`; protects your free AI quota |
   | `MAX_REVIEWS_PER_SESSION` | e.g. `5` |

6. **Resources.** The smallest compute plan available on the free tier is fine; the app needs very little.
7. **Deploy.** Northflank builds the image and starts the service. Open the public URL and review a sample contract to check it works.

From now on, every push to `main` rebuilds and redeploys automatically.

## Things to know

- **The audit log resets when the service restarts or redeploys**, because it's a SQLite file inside the container. That's fine for a portfolio demo. To keep it, attach a volume mounted at `/app/data` (check whether volumes are available on your plan). The free plan allows one addon (such as a database); if your other service already uses it, a volume or a later move to Postgres would need that slot.
- **Your other service is unaffected.** The two services build, deploy and restart independently. Use distinct names for any shared secret groups so their variables don't mix.
- **If the app shows "Demo mode"**, the AI variables aren't set or are misspelled. Check them and restart the service.
- **If reviews fail**, open the service's logs in Northflank. A `401`/`403` usually means a wrong key; `429` means the free limit was hit and the next provider was tried.
- **Before sharing the link widely**, review a few real contracts yourself and run the evals with your real provider.
