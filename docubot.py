"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import math
import re
from collections import Counter

# Shown whenever the docs do not contain enough evidence to answer
REFUSAL_MESSAGE = "I do not know based on the docs I have."

# Fraction of the query's (rarity-weighted) terms a snippet must cover to count as evidence
MIN_TERM_COVERAGE = 0.5


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Split documents into small snippets so retrieval returns only
        # the relevant parts instead of whole files
        self.chunks = self.chunk_documents(self.documents)  # List of (filename, snippet)

        # Build a retrieval index over the snippets (implemented in Phase 1)
        self.index = self.build_index(self.chunks)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Chunking
    # -----------------------------------------------------------

    def chunk_documents(self, documents):
        """
        Splits each document into paragraph-sized snippets.
        Every snippet is prefixed with its heading trail (e.g. "# Database
        Guide > ## Tables > ### users") so it keeps the context of the section
        it came from, even when it is the 2nd or 3rd block under a heading.
        Returns a list of (filename, snippet).
        """
        chunks = []
        for filename, text in documents:
            trail = []  # [(level, heading line)]
            for block in re.split(r"\n\s*\n", text):
                block = block.strip()
                if not block:
                    continue
                if block.startswith("#") and "\n" not in block:
                    level = len(block) - len(block.lstrip("#"))
                    trail = [h for h in trail if h[0] < level] + [(level, block)]
                    continue
                prefix = " > ".join(h for _, h in trail)
                snippet = f"{prefix}\n\n{block}" if prefix else block
                chunks.append((filename, snippet))
        return chunks

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, chunks):
        """
        Build a tiny inverted index mapping lowercase words to the ids
        (positions in self.chunks) of the snippets they appear in.

        Example structure:
        {
            "token": [0, 4, 17],
            "database": [23]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for chunk_id, (_, text) in enumerate(chunks):
            for word in set(self._tokenize(text)):
                index.setdefault(word, []).append(chunk_id)
        return index

    _STOPWORDS = {
        "a", "an", "the", "is", "are", "of", "to", "in", "on", "for", "and",
        "or", "how", "what", "where", "which", "do", "does", "i", "it", "we",
        "with", "from", "by", "at", "as", "be", "can", "this", "that", "my",
        "you", "there", "any", "if", "was", "were", "me", "about",
    }

    def _tokenize(self, text):
        """Lowercase, strip punctuation, drop stopwords."""
        words = re.findall(r"[a-z0-9_]+", text.lower())
        return [w for w in words if w not in self._STOPWORDS]

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        counts = Counter(self._tokenize(text))
        return sum(counts[word] for word in set(self._tokenize(query)))

    def _term_weight(self, term):
        """
        Inverse document frequency over snippets: words found in few snippets
        weigh more. A word missing from the docs entirely gets the max weight,
        since the user is asking about something we have no evidence for.
        """
        doc_freq = len(self.index.get(term, []))
        return math.log((len(self.chunks) + 1) / (doc_freq + 1)) + 1

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select the top_k most relevant snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        # Only score snippets that contain at least one query word
        candidates = set()
        for word in set(self._tokenize(query)):
            candidates.update(self.index.get(word, []))

        query_terms = set(self._tokenize(query))
        weights = {term: self._term_weight(term) for term in query_terms}
        total_weight = sum(weights.values())

        # Require evidence: a snippet must cover at least half of the query's
        # total term weight. Rare/unknown words ("pancake") weigh a lot and
        # common words ("make") weigh little, so one incidental shared word
        # is not enough, while a short query like "database connection" still
        # matches snippets about it.
        scored = []
        for chunk_id in candidates:
            filename, text = self.chunks[chunk_id]
            matched = query_terms & set(self._tokenize(text))
            if sum(weights[t] for t in matched) < total_weight * MIN_TERM_COVERAGE:
                continue
            score = self.score_document(query, text)
            if score > 0:
                scored.append((score, chunk_id, filename, text))

        # Highest score first; ties keep document order
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(filename, text) for _, _, filename, text in scored[:top_k]]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return REFUSAL_MESSAGE

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return REFUSAL_MESSAGE

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
