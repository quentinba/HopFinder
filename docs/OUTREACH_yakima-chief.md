# Message à Yakima Chief Hops — accès aux données « Survivable Compounds »

**À :** `Brewinghelp@yakimachief.com` (support brassicole/technique — c'est le
canal le plus proche de la R&D exposé publiquement)
**En copie :** `Hops@yakimachief.com` (produit/marketing, au cas où la demande
soit réorientée)
**Objet :** Access to Survivable Compounds data by variety — non-commercial hobby tool

Adresse postale : Yakima Chief Hops, 306 Division St., Yakima, WA 98902, USA —
tél. +1 (509) 457-3200. Délai de réponse annoncé : 1 à 3 jours ouvrés.

---

## Ce qu'on demande, et pourquoi cette formulation

On demande **une agrégation par variété**, pas leur base de lots. C'est
important : ils ne peuvent pas raisonnablement publier des mesures nominatives
par lot (ça touche à des fermes identifiées et à des clients), alors qu'une
moyenne par variété est exactement ce qu'ils publient déjà sous forme de
graphique dans le poster et le handbook. On leur demande donc de nous donner en
chiffres ce qu'ils diffusent déjà en image — c'est un pas beaucoup plus petit
qu'une ouverture de données.

On mentionne explicitement qu'on a vu l'API `/api/lot` et qu'on **ne l'a pas
énumérée** : c'est honnête, ça montre qu'on a compris la contrainte, et ça
évite qu'ils découvrent nos requêtes dans leurs logs en se demandant qui on est.

---

## Version à envoyer

> Subject: Access to Survivable Compounds data by variety — non-commercial hobby tool
>
> Hello,
>
> I'm a homebrewer building a small, non-commercial hobby tool that helps
> brewers pick hops by aroma chemistry rather than by name. It works from hop
> oil composition (BarthHaas and Yakima Chief public variety data) and
> odour-active compound databases, and suggests which hop will extend or
> contrast a given flavour.
>
> The piece I'd like to add is process timing: which varieties keep their
> aroma through the hot side, and which are better saved for a
> post-fermentation dry hop. Your Survivable Compounds research is by far the
> clearest work on this, and the four usage rules in the 2022 Brewer's
> Handbook are already shaping how I model it.
>
> My problem is the data itself. The survivables graph exists publicly only as
> an image, in a document marked "all rights reserved". I know some third-party
> tools reconstruct the numbers by measuring pixels off that chart — I don't
> want to do that. It produces values that aren't yours, aren't accurate, and
> would end up presented to brewers as if they were lab measurements.
>
> I did find your Lot Lookup API while looking for a cleaner route, and I want
> to be upfront about it: I looked up three lot numbers that were already
> published on the open web, to understand the data shape. I have not
> enumerated lot numbers and I don't intend to. Beyond that being the wrong way
> to treat someone else's service, per-lot values wouldn't answer my question
> anyway — the three Citra 2023 lots I saw varied by roughly 2x between T90 and
> Cryo, so no single lot represents a variety.
>
> So my question is simple: would you be willing to share the survivables
> figures **aggregated by variety** — the same values the poster chart shows,
> just as numbers rather than as a picture? A CSV with variety, compound, and
> mean value would be perfect. I'd credit Yakima Chief Hops explicitly wherever
> the data appears, state clearly that it's your measurement and not mine, and
> keep it out of anything commercial.
>
> If that's not something you can share, I'd still appreciate knowing — I'll
> fall back to a derived index computed from the public variety data you and
> BarthHaas already publish, and label it plainly as an estimate rather than
> letting anyone mistake it for your research.
>
> Two smaller questions, if whoever reads this happens to know:
>
> 1. The lot API returns survivables values without a unit. Are those ppm
>    (mg/kg) of the hop product?
> 2. The 3MH figures look high next to aggregate thiol numbers published
>    elsewhere. Is that total 3MH including bound precursors, rather than free
>    thiol?
>
> Thank you for the research — publishing the handbook at all was generous, and
> it's genuinely changed how I think about whirlpool additions.
>
> Best regards,
> Quentin
> [adresse email]
> [lien vers l'outil, si public au moment de l'envoi]

---

## Notes de rédaction

- **Ne pas demander la base de lots.** La demande porte sur une agrégation par
  variété, qu'ils diffusent déjà sous forme de graphique. Demander moins
  augmente les chances d'obtenir quelque chose.
- **Dire qu'on a touché l'API, et combien.** Trois lookups sur des numéros déjà
  publics. Le dire vaut mieux qu'ils le déduisent.
- **Dire aussi ce qu'on fait s'ils refusent.** Ça montre que la demande n'est
  pas un ultimatum et que le projet avance sans eux — ça enlève la pression et,
  paradoxalement, ça aide.
- **Les deux questions techniques valent le mail à elles seules** : même un
  refus sur les données peut s'accompagner d'une réponse sur l'unité et sur le
  3MH lié, ce qui débloquerait T116 (cf. backlog).
- Le compliment final est sincère et vérifiable (les règles du handbook sont
  effectivement reprises dans `CLAUDE.md`) — pas une formule.
