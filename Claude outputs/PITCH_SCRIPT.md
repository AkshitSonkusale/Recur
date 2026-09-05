# Recur — 5 minute pitch video

## Before you hit record

Run this once, all the way through, so nothing breaks on camera:

```
.venv\Scripts\activate
python agent\scorer.py
python data\real_world_check.py
python run_batch.py --reset
python run_batch.py
python run_batch.py
python make_dashboard.py
```

**`agent/scorer.py` must run before `run_batch.py --reset`.** If `model.pkl`
isn't there, reset crashes. That is the one way this demo dies on camera.

Then set up your screen:

- Close Slack, WhatsApp, email, notifications off
- Browser: one window, two tabs — `reports/dashboard.html` and the GitHub repo
- Terminal: font size up to ~18pt, maximised
- VS Code open on `agent/guardrails.py`, scrolled to the top
- Have `python run_batch.py --reset` already typed but **not** entered

---

## The script

Beats, not lines. Say it your way. If you read this word for word it will
sound read.

---

### 0:00 – 0:30 — who and what

> Hi, I'm Akshit, final year CS at Anurag University, and this is Recur.
>
> Recur is an agent for Track 3, revenue recovery. When a subscription
> payment fails, most companies just retry it. That is where the money
> leaks, and it's also where you can get yourself in trouble very fast.

**Screen:** README top, or your face. Keep it moving.

---

### 0:30 – 1:15 — the problem

> Here's the thing I kept coming back to. Recovering a failed payment is
> not a hard technical problem. Retrying a charge is three lines of code.
>
> The hard part is knowing when to stop. UPI Autopay has real limits.
> You get one attempt and three retries, that's it. You have to give
> twenty four hours notice before you debit someone. And if a customer
> revokes their mandate, you're done, you cannot touch that account again.
>
> Break those and you're not losing revenue anymore, you're a compliance
> problem. So I didn't build a retry bot. I built something that decides
> whether to act at all.

**Screen:** `agent/guardrails.py` — scroll slowly through the rule checks.
Don't explain the code. Let them see it's real and it's cited.

---

### 1:15 – 2:15 — run it

**Screen:** terminal. Hit enter on `run_batch.py --reset`.

> This is a batch of 76 failed transactions, about 38 lakh rupees at risk.
> Mandate failures, abandoned checkouts, overdue invoices.
>
> First run, it acts on 70 of them. Retries where a retry is still legal,
> payment links where it isn't, escalates the ones a person needs to look at.

Run it again. And again.

> Now watch what happens when I run it a second time. Thirty five.
> Third run, twenty four. Fourth, eleven.
>
> It's not getting worse at its job. It's remembering. Paid transactions
> stop being chased. Retry limits fill up. People it has already contacted
> three times get left alone.
>
> An agent that does the same thing every morning is a harassment engine.
> This one winds itself down.

**This is your best moment. Don't rush it. Let the numbers land.**

---

### 2:15 – 3:00 — the part I'd get asked about

> Two decisions I want to call out.
>
> First, the rules beat the maths. Every case gets a recovery probability
> and an expected value, and the agent picks the highest one. Except when
> a rule says no. There's a transaction in this batch where it spends
> sixty rupees escalating a 499 rupee case at five percent odds. That is a
> guaranteed loss and it takes it anyway, because the row is risk flagged.
> Sixty two of the 76 decisions here are the rules overriding the economics.
>
> Second, there is an LLM in this, and it never touches the money. By the
> time the model runs, the action is already decided, the amount is fixed,
> the link is already created. It only writes the wording, in Hinglish.
> And everything it writes gets checked before it goes anywhere. Wrong
> amount, invented link, anything threatening, anything that implies
> another debit on a cancelled mandate, it gets thrown away and a template
> goes instead. The log records that it happened.

**Screen:** dashboard, scrolled to the decision log. Expand one trace.

---

### 3:00 – 4:00 — dashboard

**Screen:** `reports/dashboard.html`, top.

> Every decision is traceable. Score, which rules fired, what it compared,
> what it picked, what it cost, what happened.
>
> This strip is the five stages. This section is the honest comparison —
> what a retry script would have done versus what this did, on the same
> batch, with live numbers.
>
> And this is the split I care about most. What it acted on, and what it
> deliberately left alone.

Scroll, don't narrate every pixel. Let it breathe.

---

### 4:00 – 4:40 — proof it isn't just my own numbers

**Screen:** run `python data\real_world_check.py`.

> One last thing. The batch is generated, because nobody publishes a
> dataset of failed UPI mandates. So the accuracy number is measured
> against outcomes I wrote, which isn't much of a test.
>
> So I pointed the same model at 30,000 real customer repayment histories
> from a public UCI dataset. Different country, different instrument, real
> outcomes. It scores 0.78 there, against 0.69 on my own data. It got
> better on real data, not worse.
>
> And that dataset ships with sex, education and marital status columns.
> None of them are used, and there's a test that fails if any of them
> reach the model. A collections model that keys off someone's marital
> status is a discrimination problem with a ROC curve on top.

---

### 4:40 – 5:00 — close

> Thirty one tests, all passing. Real Razorpay payment links in test mode.
> Every rule traced back to Razorpay's own Autopay documentation.
>
> I built this in a few days and I'd want to spend a lot longer on it.
> Thanks for watching.

---

## What to record with

**Xbox Game Bar** is already on your machine. `Win + G`, hit record, it
captures the active window plus your mic. Saves to `Videos\Captures`.
Zero setup. Use this unless you already have OBS.

**OBS** if you have it — better quality, and you can put a webcam bubble
in the corner.

Mic: use earphones with a mic if you have them. Laptop mic in a quiet room
is fine. Bad audio kills a pitch faster than bad video.

Face on camera: nice for the first 20 seconds and the last 20, if it's easy.
If it adds any friction, skip it. Voice over screen is completely fine.

## Where to upload

**YouTube, unlisted.** Not Google Drive. Drive permission problems are the
single most common way a submission gets marked incomplete — the judge
clicks, sees "request access", moves on.

Upload, set visibility to **Unlisted**, copy the link, paste it in the form.
Then open the link in an incognito window and confirm it plays. Do that
before you close the form.

## If you run over 5 minutes

Cut the dashboard section down to 30 seconds. It's the most cuttable part
because they can open the dashboard themselves. Never cut the run-it-again
wind-down.

## Do this

Record it twice. The first take is always stiff and you'll be 40% faster
the second time. Don't aim for perfect — aim for a person who clearly
understands what they built and why. That reads better than a polished
read-through, and it's what they're actually hiring for.
