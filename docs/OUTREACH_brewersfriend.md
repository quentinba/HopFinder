# Message à Brewer's Friend — permission de lecture des pages recette publiques

**Contact** : aucune adresse e-mail directe trouvée (page `/contact` et
`/contact/` renvoient 404 ; le lien "Contact"/"Support" du site pointe vers
`https://www.brewersfriend.com/feedback-welcome/`, un formulaire — pas
d'adresse e-mail visible dans le HTML statique). À envoyer via ce formulaire,
ou par une autre voie si l'utilisateur en trouve une (compte X/Twitter,
LinkedIn de l'équipe, etc.).

## Pourquoi ce message

`brewersfriend.com` a la donnée qui manque au projet (T136, en marge de T135) :
un corpus de recettes homebrewer **US**, avec un vrai planning de houblonnage
par recette (quantité, moment, durée — pas juste un total de recette comme le
dataset Kaggle qui en dérive). Une page recette publique typique montre par
exemple "Boil for 60 min" / "Boil for 0 min" / "Dry Hop for 4 days" — exactement
la granularité que `recipes.db` (T91, aujourd'hui uniquement MMuM,
germanophone) demande pour corriger son biais.

**Mais leurs conditions d'utilisation l'interdisent explicitement** :
« All content of the Website is subject to copyright with all rights
reserved. No portion of the Website (html, images, text content, source code)
may be mirrored, retransmitted, copied, duplicated, reposted, or otherwise
used without the written approval of BrewersFriend.com. » -- contrairement à
BarthHaas/Yakima/BeerMaverick (aucune licence publiée, traités par attribution
+ lecture seule) ou à beer-analytics.com (accord explicite déjà obtenu, T89),
ceci est une interdiction ACTIVE, pas juste une absence de licence. D'où ce
message avant tout code d'ingestion, même si `robots.txt` autorise
techniquement le crawl (`User-agent: ClaudeBot`, `Crawl-delay: 5` -- ils
pensent visiblement déjà aux agents IA, mais robots.txt régit l'indexation,
pas la réutilisation de contenu, question distincte que seules leurs
conditions tranchent).

## Version à envoyer

> Subject: Permission to read public recipe pages for hop-timing data — non-commercial hobby tool
>
> Hello,
>
> I'm a homebrewer building HopFinder, a small non-commercial hobby tool that
> helps brewers pick hops by aroma chemistry rather than by name. One feature
> shows brewers when a hop is actually added during the boil/whirlpool/dry hop,
> based on real recipes rather than guesswork — right now that's built entirely
> from one German homebrew site (maischemalzundmehr.de), which means the whole
> feature is biased toward German brewing habits and doesn't represent how hops
> are used in the US at all.
>
> Brewer's Friend is the best public source I've found for the US side of that
> — individual recipe pages show a real hop schedule (name, amount, and timing
> down to the addition, e.g. "Boil for 60 min" or "Dry Hop for 4 days"), which
> is exactly the granularity I need and something the Kaggle export of your
> data (which only has recipe-level totals) doesn't include.
>
> Your terms say no portion of the site may be copied or reused without
> written approval, so I'm asking before writing any code. What I'd want to do,
> specifically:
>
> - Read a limited number of public recipe view pages (`/homebrew/recipe/view/
>   ...`) — I'd propose starting with a few hundred to test coverage and data
>   quality, not the full catalog, and only recipes already public on the site.
> - Extract just the hop schedule (variety name, amount, boil/dry-hop stage,
>   timing) into my own database — not republish your pages, styling, or any
>   other content, and not use your `/beerxml`, `/export`, `/json`, or `/print`
>   endpoints (I saw those are disallowed in robots.txt and I'd stick to the
>   plain recipe page either way).
> - One request every 5+ seconds (matching the Crawl-delay you've already set
>   for ClaudeBot in robots.txt), a proper user agent, and a local cache so
>   each page is only fetched once.
> - Credit Brewer's Friend explicitly wherever the derived data appears, keep
>   it out of anything commercial, and share what I build if that's useful to
>   you.
>
> If you'd rather share an aggregate or export instead of having me read pages
> directly, that would work just as well or better — I really only need hop
> name, amount, and stage/timing per recipe, nothing else.
>
> If this isn't something you're able to allow, I understand and won't proceed
> — I'd still appreciate knowing either way so I can stop looking here rather
> than wonder.
>
> Thank you for building and keeping this up as a free resource for so long —
> HopFinder leans on it already just as a place to point brewers who want to
> go plan a batch.
>
> Best regards,
> [name]
> [adresse email]
> [lien vers l'outil, si public au moment de l'envoi]

## Notes de rédaction

- **Citer la clause exacte plutôt que la paraphraser** : montre qu'on l'a
  vraiment lue, pas juste deviné qu'il fallait demander.
- **Dire explicitement qu'on n'a PAS touché aux endpoints interdits par
  robots.txt** (`/beerxml`, `/export`, `/json`, `/print`) — même principe que
  le message Yakima Chief ("j'ai vu l'API, je ne l'ai pas énumérée") : montrer
  qu'on a lu leurs règles avant de demander, pas après avoir été bloqué.
- **Proposer un volume raisonnable (quelques centaines), pas "tout"** —
  demander moins augmente les chances d'un oui, et laisse la porte ouverte à
  étendre après un premier accord plutôt que de partir sur un refus.
- **Mentionner le Crawl-delay déjà présent dans leur propre robots.txt** :
  montre qu'on respecte une règle qu'ILS ont posée, pas une politesse
  générique inventée pour l'occasion.
- **Proposer l'alternative "export agrégé"** : même logique que le message
  Yakima Chief -- une donnée agrégée est souvent plus facile à accorder qu'un
  accès de lecture répété à des pages individuelles.
- **Dire ce qu'on fait s'ils refusent** : encore une fois, enlève la pression
  et montre que ce n'est pas un ultimatum -- T136 reste alors fermé sur ce
  point précis, sans bloquer le reste du projet.
