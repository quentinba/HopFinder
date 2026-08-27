# Message à Christian Scheb (auteur de beer-analytics) — LinkedIn

Contexte : on réutilise ses endpoints JSON publics (agrégats par style et par
houblon) et son dictionnaire d'alias `recipe_db/data/hops.csv`. Le message a
trois buts : prévenir avant de crawler, demander si un extrait agrégé est
envisageable (seul chemin vers des triplets/quadruplets à grande échelle), et
ouvrir la porte à une contribution en retour.

À poster en **deux messages** si LinkedIn tronque : la limite d'une invitation
avec note est de 300 caractères, mais un message direct (si vous êtes déjà en
relation, ou via InMail) accepte largement le texte ci-dessous.

---

## Version longue (message direct)

> Hi Christian,
>
> I'm a homebrewer building a small open-source hobby tool called HopFinder. It
> works from the other end than Beer Analytics: it starts from aroma chemistry —
> hop oil composition from BarthHaas and Yakima Chief, odour-active compounds
> from Flavornet/FlavorDB2 — and tries to answer "which hop matches this
> ingredient I'm adding to the beer".
>
> What it completely lacks is the empirical side: what brewers actually do. Beer
> Analytics is the best thing that exists there, by a wide margin. So two things.
>
> First, a heads-up rather than a request: I'd like to read your public per-style
> and per-hop chart endpoints (usage types, popular hops, hop pairings, the
> metric histograms) to enrich hop pages, with a single cached pass, a
> self-identifying user agent, and visible attribution back to
> beer-analytics.com. If you'd rather I didn't, or you'd prefer a different
> access pattern, just say so and I'll follow it. I'm also reusing
> recipe_db/data/hops.csv as a hop-name alias dictionary — that file saved me
> a lot of tedious work, so: thank you.
>
> Second, an actual question. I'd like to look at hop combinations of size 3 and
> 4, not just pairs (calculate_hop_pairings is pairwise by design). That needs
> recipe-level co-occurrence, which I understand you can't redistribute. Would
> you be open to either (a) exposing an aggregated n-way co-occurrence export —
> hop set, style, recipe count, nothing recipe-identifying — or (b) telling me
> it's not something you want to do? Either answer is genuinely fine; I'd just
> rather ask than scrape around you.
>
> Happy to contribute back if any of this is useful to you — I've been reading
> your analytics code closely and I'd be glad to send a PR rather than just
> take.
>
> Best,
> Quentin

## Version courte (si limite de caractères)

> Hi Christian — homebrewer here, building a small open-source hop tool
> (aroma-chemistry side: BarthHaas/Yakima oil composition, Flavornet). Beer
> Analytics is the empirical half I don't have. Two things: (1) a heads-up that
> I'd like to read your public chart endpoints, one cached pass, identified UA,
> full attribution — tell me if you'd rather I didn't; (2) would you consider an
> aggregated n-way hop co-occurrence export (hop set + style + recipe count)?
> calculate_hop_pairings is pairwise, and I'd like triplets. Happy to contribute
> back rather than just take. Thanks for the hops.csv alias file, by the way —
> it saved me hours.

---

## Notes de rédaction

- Ne rien promettre sur la non-commercialité qu'on ne tiendrait pas : le projet
  est un hobby, on le dit tel quel.
- Ne pas demander la base de recettes brute : il a explicitement écrit qu'il ne
  peut pas la redistribuer (« for legal reasons »). Demander un **agrégat**
  respecte cette contrainte au lieu de la contourner.
- Proposer une contribution est sincère et pas une formule : `hops.csv`,
  `flavors.csv` et les alias de styles gagneraient à recevoir les variétés
  BarthHaas/Yakima récentes qu'on a déjà normalisées.
