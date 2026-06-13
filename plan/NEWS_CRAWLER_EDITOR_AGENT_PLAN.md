# Plan for Building a Whitelisted News Collection System and Editor Agent

## 1. Goal

Build a controlled news collection, storage, and synthesis system that collects information only from the following approved official sources:

- `vnexpress.net`
- `vneconomy.vn`
- `cafef.vn`
- `vietstock.vn`

The system must not allow the editor agent to freely browse the open web. Every piece of information used in the final report must pass through a controlled source validation pipeline, be stored in Supabase, and then be used by the Editor Agent only as verified evidence.

---

## 2. Design Principles

### 2.1. Avoid overengineering

Do not use agents for simple deterministic tasks.

| Task | Recommended implementation |
|---|---|
| Reading RSS / sitemap | Worker / cron job |
| Filtering URLs by domain | Regular function |
| Extracting article HTML | Worker |
| Saving data to database | Backend service |
| Extracting facts/evidence from articles | LLM tool or worker that calls an LLM |
| Writing the final report | Editor Agent |
| Checking citations and source validity | Validator function |

Agents should only be used where reasoning, synthesis, editorial judgment, and language generation are actually needed.

---

## 3. High-Level Architecture

```text
User Request
   ↓
Research Planner
   ↓
Discovery Worker
   - RSS
   - Sitemap
   - Search API if needed
   ↓
Whitelist Gate
   ↓
Article Collector Worker
   ↓
Content Extractor
   ↓
Supabase Data Warehouse
   - raw_articles
   - extracted_evidence
   - research_runs
   ↓
Evidence Retriever
   ↓
Editor Agent
   ↓
Final Report with Citations
```

---

## 4. Components

## 4.1. Research Planner

Responsibilities:

- Receive the user request.
- Identify the topic, ticker, company name, industry, and time range.
- Generate search keywords.
- Do not crawl the web directly.
- Do not write the final report.

Example input:

```text
Summarize news about DHG in 2026.
```

Example output:

```json
{
  "topic": "DHG news in 2026",
  "ticker": "DHG",
  "company_name": "Dược Hậu Giang",
  "keywords": [
    "DHG",
    "Dược Hậu Giang",
    "revenue",
    "profit",
    "dividend",
    "business plan"
  ],
  "allowed_domains": [
    "vnexpress.net",
    "vneconomy.vn",
    "cafef.vn",
    "vietstock.vn"
  ]
}
```

This component can be implemented as regular code or as a simple LLM tool. A complex agent is not necessary if the task is only request parsing and keyword generation.

---

## 4.2. Discovery Worker

Responsibilities:

- Discover candidate article URLs from whitelisted sources.
- Prioritize RSS and sitemap.
- Do not crawl entire websites.
- Do not return sources outside the whitelist.

Recommended discovery priority:

```text
1. RSS feed if available
2. Sitemap / Google News sitemap if available
3. Search API with site: filters if RSS/sitemap is not enough
```

Example search queries:

```text
site:vneconomy.vn DHG profit dividend 2026
site:cafef.vn DHG business plan
site:vietstock.vn DHG financial statements
site:vnexpress.net DHG Dược Hậu Giang
```

The Discovery Worker only returns candidate URLs. It does not decide whether the content is true or write any analysis.

---

## 4.3. Whitelist Gate

Responsibilities:

- Block every URL that does not belong to the approved domains.
- Block redirects to non-approved domains.
- Block social media, forums, anonymous blogs, and unapproved aggregators.

Approved domains:

```python
ALLOWED_DOMAINS = {
    "vnexpress.net",
    "vneconomy.vn",
    "cafef.vn",
    "vietstock.vn"
}
```

Example validation function:

```python
from urllib.parse import urlparse

ALLOWED_DOMAINS = {
    "vnexpress.net",
    "vneconomy.vn",
    "cafef.vn",
    "vietstock.vn",
}

def is_allowed_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)
```

Mandatory rule:

```text
If a URL does not pass the Whitelist Gate, it must not be crawled, stored, or used in the final report.
```

---

## 4.4. Article Collector Worker

Responsibilities:

- Fetch public article pages.
- Respect `robots.txt`.
- Do not bypass paywalls.
- Do not access login-required pages.
- Do not crawl too aggressively.
- Do not crawl entire websites.

Recommended configuration:

```yaml
crawler:
  max_articles_per_run: 30
  max_requests_per_minute: 6
  timeout_seconds: 15
  retry_count: 2
  respect_robots_txt: true
  no_paywall_bypass: true
  no_login_required_pages: true
```

The collector should save:

- Original URL
- Source domain
- Article title
- Published date if available
- Accessed date
- Extracted raw text
- Optional HTML snapshot path

---

## 4.5. Content Extractor

Responsibilities:

- Extract the main content from article HTML.
- Remove menus, ads, footers, comments, and irrelevant page elements.
- Preserve important metadata.

Possible tools:

```text
Python:
- trafilatura
- BeautifulSoup
- newspaper3k if needed

Node.js:
- cheerio
- readability
```

This step does not need an agent.

Example output:

```json
{
  "source_name": "VnEconomy",
  "source_domain": "vneconomy.vn",
  "source_url": "https://vneconomy.vn/...",
  "title": "Dược Hậu Giang sets new target...",
  "published_at": "2026-06-09T00:00:00+07:00",
  "accessed_at": "2026-06-09T09:00:00+07:00",
  "raw_text": "Extracted article content...",
  "discovery_method": "sitemap",
  "extraction_method": "trafilatura"
}
```

---

# 5. Supabase Data Warehouse

Supabase is suitable for this system because it provides:

- PostgreSQL
- Full-text search
- `pgvector` if semantic search is needed later
- Supabase Storage for optional HTML snapshots
- Row Level Security if the system later supports multiple users or projects
- Auto-generated APIs for backend read/write operations

Supabase should not be used as the main crawler engine. Crawling should run in separate backend workers.

---

## 5.1. Table: `raw_articles`

Stores crawled and extracted articles.

```sql
create table raw_articles (
  id uuid primary key default gen_random_uuid(),

  source_name text not null,
  source_domain text not null,
  source_url text not null unique,

  title text,
  summary text,
  published_at timestamptz,
  accessed_at timestamptz not null default now(),

  raw_text text,
  raw_html_path text,

  discovery_method text,
  extraction_method text,

  crawl_status text default 'success',
  error_message text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Recommended indexes:

```sql
create index idx_raw_articles_domain on raw_articles(source_domain);
create index idx_raw_articles_published_at on raw_articles(published_at);
create index idx_raw_articles_title on raw_articles using gin(to_tsvector('simple', coalesce(title, '')));
create index idx_raw_articles_text on raw_articles using gin(to_tsvector('simple', coalesce(raw_text, '')));
```

---

## 5.2. Table: `extracted_evidence`

Stores factual claims extracted from articles.

This is the most important table for the Editor Agent.

```sql
create table extracted_evidence (
  id uuid primary key default gen_random_uuid(),

  article_id uuid references raw_articles(id) on delete cascade,

  topic text,
  ticker text,
  company_name text,

  claim text not null,
  evidence_text text,
  evidence_type text,

  source_name text not null,
  source_domain text not null,
  source_url text not null,

  published_at timestamptz,
  accessed_at timestamptz,

  confidence text default 'medium',

  created_at timestamptz not null default now()
);
```

Recommended indexes:

```sql
create index idx_evidence_ticker on extracted_evidence(ticker);
create index idx_evidence_topic on extracted_evidence(topic);
create index idx_evidence_source_domain on extracted_evidence(source_domain);
create index idx_evidence_published_at on extracted_evidence(published_at);
create index idx_evidence_claim_text on extracted_evidence using gin(to_tsvector('simple', coalesce(claim, '') || ' ' || coalesce(evidence_text, '')));
```

---

## 5.3. Table: `research_runs`

Stores each research request and execution history.

```sql
create table research_runs (
  id uuid primary key default gen_random_uuid(),

  user_id uuid,
  topic text not null,
  ticker text,
  company_name text,
  query text,

  allowed_domains text[] not null,

  status text default 'running',

  started_at timestamptz not null default now(),
  finished_at timestamptz,

  error_message text
);
```

---

## 5.4. Table: `research_run_articles`

Links a research run to the articles used during that run.

```sql
create table research_run_articles (
  id uuid primary key default gen_random_uuid(),

  research_run_id uuid references research_runs(id) on delete cascade,
  article_id uuid references raw_articles(id) on delete cascade,

  relevance_score numeric,
  selected boolean default false,

  created_at timestamptz not null default now()
);
```

---

## 5.5. Table: `editor_outputs`

Stores generated editorial outputs.

```sql
create table editor_outputs (
  id uuid primary key default gen_random_uuid(),

  research_run_id uuid references research_runs(id) on delete cascade,

  title text,
  report_markdown text not null,
  citation_count int default 0,

  status text default 'draft',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

---

# 6. Evidence Builder

The Evidence Builder converts article content into structured facts.

Input:

```json
{
  "title": "...",
  "raw_text": "...",
  "source_url": "...",
  "published_at": "..."
}
```

Output:

```json
{
  "facts": [
    {
      "claim": "DHG set a revenue target of VND 5,530 billion for 2026.",
      "evidence_text": "A short passage supporting this claim...",
      "evidence_type": "business_plan",
      "confidence": "high"
    }
  ]
}
```

This can be implemented as an LLM tool.

A separate agent is not necessary if the task is simply:

```text
Extract factual claims from this article into JSON.
```

Example prompt:

```text
You are an information extraction tool.

Extract factual claims from the article below.

Rules:
- Only extract facts explicitly supported by the article.
- Do not infer beyond the text.
- Each claim must have a short supporting evidence_text.
- Do not include facts without evidence.
- Return JSON only.

Fields:
- claim
- evidence_text
- evidence_type
- confidence

Article:
{article_text}
```

After the LLM returns JSON, the backend must validate:

```text
- claim is not empty
- evidence_text is not empty
- source_url belongs to the whitelist
- article_id exists
```

---

# 7. Editor Agent

The Editor Agent is the main agent responsible for writing the final report.

## 7.1. Role

The Editor Agent must not:

- Browse the web.
- Search for external sources.
- Add facts that are not supported by evidence.
- Use blogs, forums, social media, or anonymous websites.
- Use URLs outside the whitelist.

The Editor Agent may:

- Read evidence from Supabase.
- Synthesize a report.
- Add citations.
- Explicitly state when evidence is insufficient.
- Compare sources when there are conflicts.

---

## 7.2. Editor Agent Input

The Editor Agent receives an evidence packet, not raw web access.

Example:

```json
{
  "topic": "DHG news summary in 2026",
  "ticker": "DHG",
  "company_name": "Dược Hậu Giang",
  "allowed_domains": [
    "vnexpress.net",
    "vneconomy.vn",
    "cafef.vn",
    "vietstock.vn"
  ],
  "evidence": [
    {
      "claim": "DHG set a revenue target of VND 5,530 billion for 2026.",
      "evidence_text": "A short passage supporting this claim...",
      "source_name": "VnEconomy",
      "source_url": "https://vneconomy.vn/...",
      "published_at": "2026-06-09T00:00:00+07:00"
    }
  ]
}
```

---

## 7.3. System Rules for the Editor Agent

```text
You are an editor agent for financial and business news synthesis.

You are not allowed to browse the open web.

You may only use the evidence packet provided by the internal retrieval system.

Allowed source domains:
- vnexpress.net
- vneconomy.vn
- cafef.vn
- vietstock.vn

Rules:
1. Every factual claim must be supported by evidence.
2. Do not invent facts.
3. Do not use sources outside the allowed domains.
4. If evidence is missing, say that evidence is insufficient.
5. If sources conflict, explicitly mention the conflict.
6. Always cite source_name, source_url, and published_at when available.
7. Write in Vietnamese unless the user requests otherwise.
```

---

# 8. Citation Validator

After the Editor Agent writes the report, the output must pass a code-based validator.

A separate agent is not necessary.

The validator checks:

```text
- Does each citation have a source_url?
- Does each source_url belong to the whitelist?
- Does each source_url exist in the evidence packet?
- Are important claims cited?
- Are there any non-whitelisted sources?
```

If validation fails:

```text
Do not publish the report.
Return it to the Editor Agent for revision or report an insufficient-evidence error.
```

---

# 9. Real Execution Flow

## 9.1. User Request

Example:

```text
Summarize the most important DHG news from the last 6 months.
```

The backend creates a `research_run`.

```json
{
  "topic": "Important DHG news from the last 6 months",
  "ticker": "DHG",
  "allowed_domains": [
    "vnexpress.net",
    "vneconomy.vn",
    "cafef.vn",
    "vietstock.vn"
  ],
  "status": "running"
}
```

---

## 9.2. Discovery

The worker discovers article URLs from RSS, sitemap, or search.

Example sources:

```text
RSS/Sitemap:
- vneconomy.vn/sitemap/google-news.xml
- vnexpress.net/rss/kinh-doanh.rss
- cafef.vn RSS/sitemap if available
- vietstock.vn RSS/sitemap if available
```

If not enough articles are found:

```text
Search query:
site:vneconomy.vn DHG Dược Hậu Giang profit dividend
site:cafef.vn DHG Dược Hậu Giang business plan
site:vietstock.vn DHG financial statements
site:vnexpress.net DHG Dược Hậu Giang
```

---

## 9.3. Filtering

The Whitelist Gate filters domains.

```text
Allowed:
https://vneconomy.vn/...
https://cafef.vn/...

Rejected:
https://random-blog.com/...
https://facebook.com/...
```

---

## 9.4. Collection

The collector fetches HTML from each valid article URL.

The article is saved into `raw_articles`.

---

## 9.5. Evidence Extraction

The Evidence Builder reads `raw_articles.raw_text`.

It creates records in `extracted_evidence`.

---

## 9.6. Evidence Retrieval

The backend retrieves relevant evidence:

```sql
select *
from extracted_evidence
where ticker = 'DHG'
order by published_at desc
limit 30;
```

---

## 9.7. Editor Agent Report Generation

The Editor Agent receives the evidence packet and writes:

```markdown
# DHG News Summary

## Key Points

...

## Business Developments

...

## Risks to Monitor

...

## Sources

- VnEconomy, date..., URL...
- CafeF, date..., URL...
```

---

## 9.8. Citation Validation

The Citation Validator checks the report.

If it passes:

```text
Save the report to editor_outputs.
```

If it fails:

```text
Ask the Editor Agent to revise the report or return an insufficient-evidence error.
```

---

# 10. RSS/Sitemap-First Strategy

## 10.1. Why RSS/Sitemap First?

RSS and sitemap are preferred because:

- They do not require a newspaper API.
- They are less risky than crawling the whole website.
- They make source control easier.
- They are suitable for discovering recent articles.
- They make audit easier.

RSS usually provides:

```text
- title
- link
- published_at
- summary
```

RSS usually does not provide the full article body.

Therefore, RSS should be used for discovery, not as the full content source.

Correct pipeline:

```text
RSS/Sitemap
→ Get article URLs
→ Fetch article HTML
→ Extract article content
→ Store in Supabase
→ Create evidence
→ Editor Agent synthesizes from evidence
```

---

## 10.2. Example Pseudo-Code

```python
def run_research_collection(topic, keywords, allowed_domains):
    run_id = create_research_run(topic, keywords, allowed_domains)

    candidate_urls = []

    candidate_urls += discover_from_rss(keywords)
    candidate_urls += discover_from_sitemaps(keywords)

    if len(candidate_urls) < 10:
        candidate_urls += discover_from_search_api(keywords, allowed_domains)

    allowed_urls = [
        url for url in candidate_urls
        if is_allowed_url(url)
    ]

    unique_urls = deduplicate_urls(allowed_urls)

    for url in unique_urls[:30]:
        article = collect_article(url)

        if article:
            article_id = save_raw_article(article)
            evidence_items = extract_evidence(article)
            save_evidence(article_id, evidence_items)

    mark_research_run_completed(run_id)

    return run_id
```

---

# 11. What Not To Do

Do not:

```text
- Let the Editor Agent search Google directly.
- Let any agent read arbitrary internet sources.
- Crawl entire websites.
- Ignore robots.txt.
- Bypass paywalls.
- Store data without source_url.
- Write reports without citations.
- Let the LLM decide which sources are trustworthy if the whitelist is already defined.
- Use agents for tasks that only need functions or workers.
```

---

# 12. Is an API Required?

A newspaper API is not required.

The system can use:

```text
RSS/Sitemap + lightweight scraper
```

If stronger search is needed, use:

```text
Google Custom Search API
or another search provider
```

However, the search API should only be used to discover URLs. It should not be treated as the source of truth.

The source of truth must be:

```text
Original article content from whitelisted domains.
```

---

# 13. Implementation Roadmap

## Phase 1: MVP

Goal: build an end-to-end pipeline from URL discovery to final report.

Tasks:

```text
1. Create Supabase schema:
   - raw_articles
   - extracted_evidence
   - research_runs
   - editor_outputs

2. Implement whitelist URL validator.

3. Implement RSS/Sitemap discovery for at least 1–2 sources.

4. Implement article collector.

5. Implement content extractor.

6. Save raw_articles into Supabase.

7. Create Evidence Builder using an LLM tool.

8. Create Editor Agent that only reads evidence packets.

9. Create a simple Citation Validator.
```

MVP does not need:

```text
- pgvector
- complex queues
- complex multi-agent architecture
- large dashboard
- distributed crawler
```

---

## Phase 2: Stabilization

Add:

```text
- Job scheduler / cron
- Retry logic
- Better duplicate detection
- Article freshness checks
- Better date extraction
- Per-domain extractor configuration
- Error logging
- Rate limits per domain
```

---

## Phase 3: RAG Upgrade

Only implement this after the MVP is stable.

Add:

```text
- pgvector embeddings for raw_articles or evidence
- Semantic retrieval by topic
- Evidence ranking
- Conflict detection
- Report versioning
```

---

# 14. Final Recommendation

The most suitable design is:

```text
Whitelist-based news collection
+ RSS/Sitemap-first discovery
+ lightweight article scraper
+ Supabase data warehouse
+ LLM-based evidence extraction
+ Editor Agent only for synthesis
+ code-based citation validation
```

Do not turn the whole system into a complex multi-agent architecture.

Use agents only at the editorial/synthesis layer. Crawling, URL filtering, database storage, and citation validation should be handled by workers and regular functions.
