# DocuBot Model Card

This model card is a short reflection on the DocuBot system as it currently works. The retrieval results below were produced by running the code against the `docs/` folder. The Naive LLM and RAG columns were **not run**, because no `GEMINI_API_KEY` was available when this card was written; those cells are marked as such rather than guessed.

---

## 1. System Overview

**What is DocuBot trying to do?**  
DocuBot answers developer questions about a small project using only the project's own documentation (`docs/*.md`, `docs/*.txt`). It retrieves the few most relevant snippets, optionally has Gemini turn them into an answer, and says "I do not know based on the docs I have." when the docs don't contain enough evidence.

**What inputs does DocuBot take?**

- A natural language question (a single custom query, or the built-in `SAMPLE_QUERIES` in `dataset.py`)
- The documentation files in the `docs/` folder (AUTH.md, API_REFERENCE.md, DATABASE.md, SETUP.md)
- The `GEMINI_API_KEY` environment variable (or `.env` file) to enable the LLM modes. Without it, only retrieval-only mode works.

**What outputs does DocuBot produce?**

- Retrieval only: up to 3 raw snippets, each labelled with its filename and prefixed with its heading trail, or the refusal message.
- RAG: a short Gemini-written answer that cites the files it used, or the refusal message.
- Naive LLM: a free-form Gemini answer to the question. In the current code the docs are not actually sent to the model.

---

## 2. Retrieval Design

**How does your retrieval system work?**

- **Chunking.** Each document is split on blank lines into paragraph-sized snippets. Every snippet is prefixed with its heading trail (for example `# Database Guide > ## Tables > ### users`) so it keeps the context of its section. Headings alone are not snippets.
- **Index.** An inverted index maps each lowercase word to the ids of the snippets that contain it. Text is tokenized with a regex (`[a-z0-9_]+`, so `user_id` stays one token) and a small stopword list is removed.
- **Scoring.** A snippet's score is the total number of times the distinct query words appear in it.
- **Choosing snippets.** Only snippets containing at least one query word are considered. Each query word gets a rarity weight (inverse document frequency over snippets; a word that appears nowhere in the docs gets the maximum weight). A snippet is kept only if the words it contains make up at least 50% of the query's total weight. The survivors are sorted by score (ties in document order) and the top 3 are returned.

**What tradeoffs did you make?**

- **Simplicity vs accuracy.** Exact word matching with no stemming or synonyms is easy to read and debug, but it misses different forms of the same word (see failure cases).
- **Small snippets vs completeness.** Paragraph-sized snippets save tokens, but a answer can be split across snippets (for example a heading, an intro sentence and a table), so the best snippet sometimes lacks part of the question's vocabulary.
- **Heading trails vs size.** Adding the heading trail to every snippet fixed the case where a table did not mention "users" anywhere. It also made snippets longer, and it makes section words like "database" appear in many snippets, which lowers their weight.
- **Strict vs lenient refusal.** The 50% weighted-coverage rule stops one incidental shared word (like "make") from producing a confident but irrelevant snippet. The cost is that it now refuses some legitimate questions.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**

- **Naive LLM mode:** Calls Gemini on every question with no retrieval. The current `naive_answer_over_full_docs` ignores the `all_text` argument and sends only the question, so the model answers from general knowledge, not from the docs.
- **Retrieval only mode:** Never calls the LLM. It prints the retrieved snippets, or the refusal message if nothing passes the evidence check.
- **RAG mode:** Calls Retrieval first. If no snippets pass the evidence check, it returns the refusal message without calling Gemini (no tokens spent). Otherwise it sends the question plus only the retrieved snippets to Gemini. API errors are caught and returned as a message.

**What instructions do you give the LLM to keep it grounded?**  
The RAG prompt tells the model to act as a cautious documentation assistant and to:

- use only the information in the provided snippets;
- not invent functions, endpoints or configuration values;
- reply exactly "I do not know based on the docs I have." if the snippets are not enough;
- briefly mention which files it relied on.

---

## 4. Experiments and Comparisons

The Retrieval only column reflects what the code returned. The Naive LLM and RAG columns were not run (no API key).

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Not run | Helpful: returns AUTH.md snippets (first one is the Environment Variables section that mentions generation) | Not run | The "Token Generation" snippet naming `generate_access_token` is not guaranteed to be first. |
| How do I connect to the database? | Not run | Harmful (misleading refusal): "I do not know" | Not run (RAG would also refuse, since retrieval returns nothing) | The docs cover this, but the question says "connect" and the docs say "connection". |
| Which endpoint lists all users? | Not run | Partly helpful: returns only the API_REFERENCE.md intro snippet | Not run | The actual `GET /api/users` section is missed; "lists" does not match "list". |
| How does a client refresh an access token? | Not run | Helpful: returns the AUTH.md Client Workflow snippet that mentions `/api/refresh` | Not run | Does not return the `POST /api/refresh` section of API_REFERENCE.md. |
| Which fields are stored in the users table? | Not run | Harmful (misleading refusal): "I do not know" | Not run (RAG would also refuse) | `fields`/`stored` do not match the table's words (`Column`, `Stores`). |
| What does the /api/projects/<project_id> route return? | Not run | Harmful (misleading refusal): "I do not know" | Not run (RAG would also refuse) | The route is documented, but "return" vs "Returns" and "route" are unmatched rare words. |
| Is there any mention of payment processing? | Not run | Helpful: correctly says "I do not know" | Not run | Correct refusal. |
| How do I make a pancake? | Not run | Helpful: correctly says "I do not know" | Not run | An earlier version returned an unrelated DATABASE.md snippet because "make" matched "to make debugging easier". Fixed with rarity weighting. |

**What patterns did you notice?**

- **When does naive LLM look impressive but untrustworthy?** In the current code it never sees the docs, so any fluent answer is general knowledge and could be wrong for this project. (Observed from reading the code, not from running it.)
- **When is retrieval only clearly better?** For questions the docs clearly answer with matching vocabulary, and for off-topic questions. It is deterministic, free, and cannot invent anything. The returned text is exactly what the docs say.
- **When is RAG clearly better than both?** Not tested. By design it should help when the answer is spread over several snippets and needs summarising, but it depends on retrieval, so every retrieval miss above would also be a RAG miss.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**

> **Failure case 1: false refusal from word-form mismatch.**
> Question: "How do I connect to the database?" (also "Which fields are stored in the users table?")
> What the system did: Replied "I do not know based on the docs I have."
> What should have happened: Returned the DATABASE.md connection section and the users table. The docs use "connection", "Column" and "Stores", while the query used "connect", "fields" and "stored". Exact word matching treats these as different words, and the unmatched words get a high rarity weight, which pushes coverage under 50%.

> **Failure case 2: wrong snippet from one incidental word (fixed).**
> Question: "How do I make a pancake?"
> What the system did (before the fix): Returned a DATABASE.md snippet containing "to make debugging easier".
> What should have happened: Refuse. Fixed by weighting rare/unknown words so "pancake" (not in the docs) outweighs the common word "make".

> **Failure case 3: answer split across snippets.**
> Question: "Which column in the users database stores the users email?"
> What the system did (before the fix): Returned nothing, because the table snippet had lost the "users" heading and only matched "column" and "email".
> What should have happened: Return the users table. Fixed by adding the heading trail to every snippet.

**When should DocuBot say "I do not know based on the docs I have"?**

- The question is about something the docs never mention (payment processing, weather, cooking).
- The question only shares generic words with the docs (such as "make" or "return"), so there is no real evidence that the snippet answers it.
- In RAG mode, when retrieval finds snippets that look related but do not actually state the answer (the LLM is instructed to refuse in that case).

**What guardrails did you implement?**

- A weighted evidence threshold: snippets must cover at least 50% of the query's rarity-weighted terms (`MIN_TERM_COVERAGE`).
- A single shared refusal message (`REFUSAL_MESSAGE`) used by both retrieval-only and RAG modes.
- RAG skips the LLM entirely if retrieval is empty.
- A grounding prompt that restricts Gemini to the retrieved snippets and requires an exact refusal string and file citations.
- A limit of 3 small snippets per question to keep token use low.
- API errors are caught and reported instead of crashing.

---

## 6. Limitations and Future Improvements

**Current limitations**

1. No stemming or synonyms: "connect" vs "connection", "fields" vs "Column", and "returns" vs "return" do not match, which causes false refusals (Failure case 1).
2. Frequency weights are computed from only about 120 snippets, so they are rough, and heading trails make section words like "database" and "api" look common.
3. Snippets split on blank lines, so a heading, an explanatory sentence and a table can end up in different snippets; some answers (for example the `GET /api/users` section) are not retrieved at all.
4. The 50% threshold and 3-snippet limit are hand-picked and untested on a larger or different set of docs.
5. The naive LLM mode does not actually use the docs, so it is not a fair "full docs" baseline, and the Naive LLM and RAG modes have not been evaluated here.

**Future improvements**

1. Add light stemming (strip common endings like -s, -ed, -ing, -ion) so word forms match, and re-check the sample queries.
2. Merge a short intro paragraph with the table or code block that follows it, or retrieve neighbouring snippets, so answers are not split.
3. Run all three modes with an API key on the sample queries, fill in the table, and extend `evaluation.py` with expected refusals (such as the payment and pancake queries) so the 50% threshold can be tuned with data.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
A false "I do not know" can make a developer believe something is undocumented when it is (as with the database connection question). A confident but wrong or incomplete answer, especially from the naive LLM mode or an LLM summarising a partial snippet, could lead someone to the wrong environment variable, endpoint or table column. The docs themselves may also be out of date, and DocuBot has no way to know.

**What instructions would you give real developers who want to use DocuBot safely?**

- Treat answers as pointers to the docs, not as truth. Check the cited file before acting, especially for security-related items such as secrets, tokens and permissions.
- A refusal means "DocuBot did not find it", not "it is not documented." Rephrase the question using words from the docs or search the files directly.
- Prefer retrieval only or RAG over naive mode when the answer must be specific to this project.
- Keep the docs current. DocuBot is only as accurate as the files in `docs/`.

---
