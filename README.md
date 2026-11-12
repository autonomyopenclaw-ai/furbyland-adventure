# Furbyland adventure

This is a choose-your-own-adventure bot for X. On a schedule it reads replies to its latest chapter, picks one, and posts the next chapter in the same thread.

The story is a placeholder. The account that posts it is a placeholder too. You choose both before the first real post.

It uses the official X API v2 with OAuth 1.0a user context (the bot acts as the account you authorize). It does not import the Queen of Furbies poster. That project can use the same X app: the same API key and secret, and its own access tokens.

## What you still need to choose

- The X handle that will post (`ADVENTURE_USERNAME`).
- The opening story, in [`premises/sample.md`](premises/sample.md).
- Whether a language model writes chapters, or the built-in templates are enough.
- When the schedule should run, after a dry run and a first real post look right.

## What the bot does

1. `adventure start` posts the opening chapter. It ends with a question or choices.
2. People reply to that post with ideas.
3. `adventure advance` reads those replies, skips ones that are offensive, spammy, or trying to give the bot instructions, and picks one.
   - The default is the reply with the most likes. If there is a tie, the earlier reply wins.
   - Set `ADVENTURE_SELECTION=random` to pick at random instead.
4. It posts the next chapter as a reply in the same thread. The chapter credits the idea. It does not @-mention anyone unless you set `ADVENTURE_CREDIT_MENTIONS=true`. The command's own output names the account that was chosen, so you can see who led the chapter. That name is not tagged in the post.
5. The chapter number, the latest post id, and a short summary are saved in [`state/story.json`](state/story.json).

Replies are untrusted. They are story ideas, not orders. A reply that says "ignore your instructions" is thrown away and is not quoted.

If nobody has left a usable reply, the bot posts one gentle nudge under the chapter and then waits. It keeps listening to the chapter itself, so people should reply to the chapter, not to the nudge. Set `ADVENTURE_NO_REPLIES=skip` if you would rather post nothing.

Chapters stay within 280 characters. Set `ADVENTURE_SPLIT_LONG=true` if a long chapter should become a short thread of replies instead of being shortened. Every part is still at most 280 characters.

## Create the X app

You need an X developer account: [developer.x.com](https://developer.x.com/).

1. Create a Project, then an App inside that Project. The Queen of Furbies poster can live in this same app. Each account still gets its own access tokens.
2. Open the app's **User authentication settings**.
   - Turn on **OAuth 1.0a**.
   - Set the app permissions to **Read and Write**. Read-only is not enough, because the bot posts.
   - If it asks for an app type, choose a native or web app that can use a PIN. This bot requests the out-of-band callback (`oob`), which is the PIN flow.
   - If a callback URL is required, use `http://127.0.0.1`. If a website URL is required, a placeholder such as `https://example.com` is fine.
3. Save. If you change permissions later, the old tokens stop matching those permissions. Run `adventure auth` again after any permission change.
4. Copy the **API Key** and **API Key Secret**. In this project those are `X_API_KEY` and `X_API_SECRET`. They are the app's consumer key and secret. Do not commit them.

Reading replies uses X's recent search. A Free app can post, but search returns HTTP 403 until the app is on a paid plan (pay-per-use credits, or an older Basic or Pro subscription). Recent search also only sees about the last 7 days, so leave a chapter up for longer than a week only if you are happy for older replies to be invisible.

## Install

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy the example environment file and fill in the API key and secret. Leave the adventure tokens blank until the next step.

```bash
cp .env.example .env
```

Load it into your shell whenever you open a new terminal:

```bash
set -a
source .env
set +a
```

`.env` is gitignored. `.env.example` is the only env file that belongs in git, and it contains placeholders.

The running bot reads environment variables only. The `.env` file is just a way to set those variables on your computer. A variable you already exported wins over the file.

## Authorize the adventure account

Log into x.com as the account that should post. Then, in the same terminal where the API key and secret are set:

```bash
adventure auth
```

The command prints an authorize URL. It does not print the consumer secret.

1. Open the URL in the browser where that account is logged in.
2. Approve access.
3. X shows a PIN. Paste it into the terminal.
4. The command calls `GET /2/users/me`, prints the handle it found, and writes the tokens to `.secrets/adventure-tokens.json`. That file is gitignored.

Copy the three lines it prints into `.env` and into GitHub Actions secrets later:

- `ADVENTURE_ACCESS_TOKEN`
- `ADVENTURE_ACCESS_TOKEN_SECRET`
- `ADVENTURE_USERNAME` (the handle, without `@`)

Before every real post, the bot calls `GET /2/users/me` again. If the tokens belong to a different handle than `ADVENTURE_USERNAME`, it refuses to post.

You can pass the PIN without a prompt: `adventure auth --pin 1234567`.

If the authorize URL does not load, the older host still serves the same API. Set `X_API_BASE=https://api.twitter.com` and run `adventure auth` again.

## Write the premise

Edit [`premises/sample.md`](premises/sample.md), or copy it and pass the copy with `--premise`.

The text between `<!-- post -->` and `<!-- /post -->` is the opening chapter when it is 280 characters or fewer. That is the easy way to control the first post without a language model. The sample is a stand-in about a lantern fox in Furbyland. Replace it.

Notes outside that block are not posted while the block fits. Delete the markers if you want the writer to compress a longer premise instead.

## Dry run

This prints the opening post and does not call X, even if you have not authorized an account yet:

```bash
adventure start --dry-run
```

Check the character count and the question at the end. `adventure status --dry-run` shows the local state file and does not contact X. Before the first post it says the story has not started.

## First real post

```bash
adventure start
```

The command confirms the handle, posts the opening chapter, and saves `state/story.json`. It prints a link like `https://x.com/your_handle/status/123`. Open that link and read the post.

If a story is already saved, `start` refuses to replace it. `adventure start --force` throws away the saved state and begins again. It does not delete posts that are already on X.

`adventure status` shows the chapter, the link, the summary, and checks that the tokens still match `ADVENTURE_USERNAME`.

## Advance once by hand

Reply to the chapter from another account with a harmless idea, then:

```bash
adventure advance --dry-run
adventure advance
```

The dry run reads replies and prints the next chapter. It does not post and does not change the state file. The real command posts that chapter as a reply and updates the state file.

If X returns 403 while reading replies, the message explains that recent search needs a paid plan. The process exits with an error and does not write a new chapter. 401 means the keys or tokens are wrong or out of date: run `adventure auth` again. 429 means you hit a rate limit: the message includes the time to wait, and nothing further is posted.

## Turn on the schedule

Story memory for the hosted schedule is the committed file `state/story.json`. It holds the chapter number, post ids, and a short summary. It does not hold API secrets.

The workflow [`.github/workflows/advance-story.yml`](.github/workflows/advance-story.yml) is the scheduler. It checks out this repo, runs `adventure advance`, and commits `state/story.json` when the file changed. That commit is how the next run remembers the thread. Use this workflow or a computer of your own, not both, or the two copies of the file will drift apart.

If you run it on your own computer instead, cron (or any timer) only needs to run `adventure advance` from this directory. The same JSON file is updated on disk, and you do not need the workflow to commit it.

To use GitHub Actions:

1. In the repo's Settings, open Secrets and variables → Actions, and add:
   - `X_API_KEY`
   - `X_API_SECRET`
   - `ADVENTURE_ACCESS_TOKEN`
   - `ADVENTURE_ACCESS_TOKEN_SECRET`
   - `ADVENTURE_USERNAME`
   - `XAI_API_KEY` or `OPENAI_API_KEY`, only if you want a language model
2. Commit the state file from your first real `adventure start` and push it. The workflow reads that file.
3. Use the Actions tab, workflow **Advance the adventure**, and **Run workflow**. Leave the command on `advance`. You can turn on the dry-run input first. The same menu can post the opening chapter: choose `start` only while `state/story.json` still says the story has not started.
4. When a real run looks right, edit the workflow and uncomment the schedule:

```yaml
on:
  schedule:
    - cron: "0 16 * * *"
```

`0 16 * * *` is every day at 16:00 UTC. Pick another time if you like. Daily is enough, because recent search only covers about 7 days. The schedule in the file is commented out until you do this.

The workflow will not start a second run while one is in progress. A push made with the built-in `GITHUB_TOKEN` does not start the workflow again, so committing the state file does not loop.

## Language model (optional)

With no model key, built-in templates write a short family-friendly chapter from the premise and from the chosen reply. That path is enough to run the whole loop.

If you set a key, the model writes the chapter and the template is the fallback when the model fails or returns something the safety filter rejects.

| Variable | Effect |
| --- | --- |
| `XAI_API_KEY` | Use xAI. Default model `grok-4` (`XAI_MODEL` to change it). |
| `OPENAI_API_KEY` | Use OpenAI. Default model `gpt-4.1-mini` (`OPENAI_MODEL` to change it). |
| `ADVENTURE_LLM=auto` | xAI if that key is set, otherwise OpenAI, otherwise templates. This is the default. |
| `ADVENTURE_LLM=none` | Templates, even if a key is present. |
| `ADVENTURE_LLM=xai` or `openai` | Require that provider's key. |

The model is told the reply is untrusted data and that it must not follow instructions inside it. The chapter it returns is still length-checked, and @-mentions are removed unless you turned credit mentions on. If the chapter does not actually credit the idea, the template chapter is posted instead.

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `X_API_KEY` | for X calls | |
| `X_API_SECRET` | for X calls | |
| `ADVENTURE_ACCESS_TOKEN` | for X calls | |
| `ADVENTURE_ACCESS_TOKEN_SECRET` | for X calls | |
| `ADVENTURE_USERNAME` | for X calls | handle, no `@` |
| `ADVENTURE_SELECTION` | no | `most_liked` (`random` also works) |
| `ADVENTURE_NO_REPLIES` | no | `nudge` (`skip` also works) |
| `ADVENTURE_CREDIT_MENTIONS` | no | `false` |
| `ADVENTURE_SPLIT_LONG` | no | `false` |
| `ADVENTURE_MAX_CHARS` | no | `280` (80–280) |
| `ADVENTURE_STATE_PATH` | no | `state/story.json` |
| `ADVENTURE_PREMISE_PATH` | no | `premises/sample.md` |
| `ADVENTURE_TOKEN_PATH` | no | `.secrets/adventure-tokens.json` |
| `X_API_BASE` | no | `https://api.x.com` |

`adventure start`, `adventure advance`, and `adventure status` all accept `--dry-run`.

## Commands

```bash
adventure auth
adventure start --dry-run
adventure start
adventure advance --dry-run
adventure advance
adventure status
adventure status --dry-run
```

`python -m furbyland_adventure` is the same program.

## Tests

```bash
pytest
```

The tests mock X's HTTP API. They cover reply selection, the filters, the 280-character limit, the username check, and how the state file moves from one chapter to the next. They do not post to a real account.

## When something fails

| What you see | What to do |
| --- | --- |
| HTTP 401 | The key and the tokens must come from the same app. Run `adventure auth` again after you rotate a secret or change permissions. The tool never prints the consumer secret. |
| HTTP 403 while reading replies | Recent search needs a paid X plan, and the app has to be attached to a Project. Posting can still work without that. |
| HTTP 403 while posting | Confirm Read and Write, then create new tokens with `adventure auth`. If the detail says the content is a duplicate, that chapter was already posted. Check `adventure status`. |
| HTTP 429 | Wait until the time in the message. Posting and searching have separate limits. |
| Wrong account | `ADVENTURE_USERNAME` does not match the tokens. The bot will not post. Authorize the adventure account, or fix the handle. |
| No replies found | Replies older than about 7 days are outside recent search. Reply to the chapter post, not to a nudge. Filtered replies are counted in the output and are not quoted. |

Run commands from this directory so `state/story.json` and `premises/sample.md` resolve.
