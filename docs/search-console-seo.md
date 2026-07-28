# Search discovery operations

The repository and release tooling can verify origin HTML, robots, sitemap XML,
canonicals, status codes, and contextual links. Google Search Console and
Cloudflare account changes are operator actions and must not be guessed or
encoded in source control.

## Release baseline

Before a production SEO release, record:

- the effective edge response for `GET` and `HEAD /robots.txt`;
- sitemap index and shard fetch status;
- raw-HTML paper/entity link counts for the homepage and representative entity
  pages;
- the previous 28 days of Search Console page/query results for
  `/paper/2607.24653`.

Keep screenshots and exports in the private release issue or operational log if
they expose account owners, property membership, or other account information.

## Google Search Console account actions

1. Open the `paperswithcode.co` **domain property** and record its verified
   owner and current least-privilege access list.
2. If the property is not verified, request the exact Google DNS TXT token and
   add that value through the authoritative DNS provider. Never invent, commit,
   or replace unrelated TXT records.
3. Submit `https://paperswithcode.co/sitemap.xml`. Record submission time,
   first successful fetch, sitemap-index type, discovered URL count, and error
   samples.
4. Inspect `https://paperswithcode.co/paper/2607.24653`, one recent ordinary
   paper, and one historical paper. Record live-fetch availability, declared
   and selected canonical, indexing state, rendered title/abstract, structured
   data, and referring sitemap.
5. If the Kimi K3 live test succeeds, request indexing once. Do not use the
   Indexing API for ordinary paper URLs or repeatedly resubmit the page.

These steps require Search Console and DNS access and therefore cannot be
completed by a repository-only release.

## Cloudflare account actions

After production application and nginx activation, fetch the public
Cloudflare-edge `robots.txt`, not only the origin:

- confirm `Content-Type: text/plain`, no HTML, and exactly one canonical
  `Sitemap:` directive;
- confirm search crawling remains allowed;
- confirm the existing managed content signals still express
  `search=yes, ai-train=no, use=reference`;
- confirm configured managed AI-crawler blocks remain present.

If Cloudflare prepends or merges managed content, adjust the Cloudflare managed
robots/content-signals setting so the effective response satisfies those stable
outcomes. Do not copy Cloudflare's evolving crawler list into application
source.

## Weekly measurement

For at least four weeks after activation, compare 7-day and 28-day windows for:

- `Kimi K3 technical report`, `Kimi K3 arxiv`, `Kimi K3 paper`, and title
  variants;
- page clicks, impressions, CTR, average position, indexed state, crawl
  response classes, canonical mismatches, and title rewrites;
- discovery lag from database publication to first Google crawl.

Annotate release dates and segment by query, page, country, device, and sitemap
when volume permits. A sitemap is a discovery hint, not a ranking guarantee.
