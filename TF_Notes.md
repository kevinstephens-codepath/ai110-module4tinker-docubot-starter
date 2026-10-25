# DocuBot
## Setup
Checked .gitignore to make sure key wouldn't be saved, then changed .env.example -> .env and added gemini key.  
Created virtual environment and requirements, main.py runs properly.
## Part 1
I input the 3 questions on naive LLM mode. Here are the results:   
Q: Where is the auth token generated?  
A: To tell you where the auth token is generated, I need a little more context! 

Could you please share:
* The programming language, framework, or specific service you are working with (e.g., Node.js, Python, Firebase, Auth0, a custom backend)?
* Any relevant code snippets or documentation files you are currently looking at?

Once you provide that, I'll be happy to pinpoint the exact file, function, or service responsible for token generation.

Q: Which endpoint returns all users?  
A: To answer your question accurately, I need a bit more context. 

Could you please provide the API documentation, OpenAPI/Swagger spec, or the route file for the project you are working on? Once you share that, I'll be happy to find the correct endpoint for you!

Q: How do I connect to the database?  
A: To connect to the database, you will need the following information:

1. **Database Credentials:** Ensure you have your `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
2. **Environment Variables:** Set these credentials in your `.env` file (copy from `.env.example` if available):
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=your_database_name
   DB_USER=your_username
   DB_PASSWORD=your_password
   ```
3. **Connection Initialization:** Use your project's established ORM or database client (e.g., Prisma, Mongoose, SQLAlchemy, or pg) to initialize the connection. 

*If your project uses a specific framework or library, please let me know so I can provide the exact code snippet!*

**Of note is the 3rd answer, which does provide more information rather than stating it needs more context**  

Skimmed /docs and saw the general information and format. DocuBot could have broadly answered the questions presented, but chose to ask for more context. The current CLI version does not have capability of back and forth context chat.

> Q. What part of the answer was unsupported, and what evidence would retrieval need to supply?  
> A. The unsupported parts were auth token gen, and specific endpoint, since those are specialized to the project that the documents refer to. For those answers retrival would have to point to AUTH.md for the first, and API_REFERENCE.md for the second.
## Part 2
Implemented build_index, score_document, and retrieve. Used regex to tokenize and it returns different documents on different queries.  
Ran retrieval mode and the queries are given proper retrivals from the documents. No need to edit.  

> Q. Which query gave the clearest retrieval result, and why did your scoring logic prefer it?  
> A.  "Which endpoint returns all users?" gave the api_reference.md result, which has the exact information an LLM would need to properly answer the question. The logic prefered it due to the number of matching tokens between the document and the query.
## Part 3
Refactored the retrival to only retrieve relevent snippets with Claudes help to lower token usage, then we worked on the specific refusal to make sure queries don't go to the LLM when there is not enough context, I attempted the question "How do I make a pancake?" as our "This shouldn't go to the LLM" example, at first it was retrieving snippets based on the "make" token since that exists in the docs. We went over a few options to weigh out the query based on the rarity of the tokens rather than the how much of the question is relevant to the documents, that way we could weigh out many irrelavant questions and keep our bot from pinging our LLM with too many non relavant queries :)

> Q.What threshold or snippet choice made the guardrail trigger, and what did the refusal look like?  
> A.  How to establish a database connection? is the main control I used, and the guardrail trigger I came up with is "How to make a pancake?" as this is obviously not covered in our documents. At first retrieval returned a snippet that included "make" due to how tokens were weighed, but after a bit of tweaking the weights based on the rarity of the word in the documents, we were able to get retrival working quite well on these sample queries.
## Part 4
Query where naive tries to answer is "How do I build a house?" It answers confidently without any grounding.
Query where retrival accurate but hard to read: "Missing database_url" gives accurate snippets, but it's hard to read as a user, the information is just displayed without context on how to use it.  
Query where RAG still fails: "What is our projects name?" This returns "Alpha Project" due to an example API request in API_REFERENCE.md -> The RAG uses that as a source of truth therefore the LLM will take that as an actual project name rather than retrival recognizing that the project has no name in the documentation.

> Q. Which mode was easiest to trust on one question, and what did the other modes miss?  
> A. Mode 1 will seemingly try to answer any question, and mode 2 only gives you documents/snippets that don't really give a good answer. Mode 3 is the easiest to understand and let's you know cleanly if it doesn't have an answer to your question. RAG as a whole is a good grounding method, however RAG does fall apart when something isn't fully labeled right, such as an example reference being used as a source of truth for real information.