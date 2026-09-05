# Recur — cue card

Phone or printed, beside the keyboard. Glance, don't read.

---

## 0:00 — open
- Akshit, final year CS, Anurag University
- Recur. Track 3, revenue recovery
- Payment fails → most people just retry → that's where money leaks

## 0:30 — the problem  `[screen: guardrails.py]`
- Recovering a payment isn't hard. Retrying is three lines
- **Hard part is knowing when to stop**
- 1 attempt + 3 retries. 24h notice. Revoke = you're done
- Break those and you're a compliance problem, not a revenue one
- So: not a retry bot. Something that decides whether to act at all

## 1:15 — RUN IT  `[screen: terminal]`
- 76 transactions, ~38 lakh at risk
- Run 1 → **acts on 70**
- Run 2 → **35**
- Run 3 → **24**
- Run 4 → **11**
- Not getting worse. Remembering
- Paid ones stop being chased. Limits fill up
- An agent that does the same thing every morning is a harassment engine
- **This one winds itself down**

> SLOW DOWN HERE. This is the best part. Pause after "winds itself down."

## 2:15 — two decisions  `[screen: dashboard → expand a trace]`

**Rules beat the maths**
- Every case gets a probability and an expected value
- Picks the highest — unless a rule says no
- ₹60 to escalate a ₹499 case at 5% odds. Guaranteed loss. Takes it anyway
- 62 of 76 decisions = rules overriding economics

**The LLM never touches the money**
- Action decided, amount fixed, link created — *then* the model runs
- It only writes wording. Hinglish
- Checked before sending: wrong amount, invented link, anything threatening,
  anything implying a debit on a cancelled mandate
- Fails → template instead, and the log says so

## 3:00 — dashboard  `[scroll, don't narrate]`
- Every decision traceable: score → rules → comparison → pick → cost → outcome
- Five-stage strip
- Retry script vs this, same batch, live numbers
- Acted on vs deliberately left alone ← linger here

## 4:00 — real data  `[screen: python data\real_world_check.py]`
- Batch is generated. Nobody publishes failed UPI mandate data
- So accuracy on it is measured against outcomes I wrote. Not a test
- Pointed the same model at 30,000 real repayment histories, public UCI dataset
- **0.78 there vs 0.69 on mine. Better on real data, not worse**
- Dataset ships with sex, education, marital status. None used
- Test fails if any reach the model
- A collections model keyed off marital status is a discrimination problem
  with a ROC curve on top

## 4:40 — close
- 31 tests passing
- Real Razorpay payment links, test mode
- Every rule traced to Razorpay's own Autopay docs
- Built it in a few days, would want a lot longer
- Thanks

---

## Voice notes

- **Pause after every bolded line.** Silence reads as confidence
- Vary the pace. Slow on the numbers, quicker on the setup
- If you fumble a sentence, stop, breathe, say it again. You're editing nothing —
  just re-record the take
- Smile on the first and last line. It's audible
