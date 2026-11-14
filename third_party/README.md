# Maintainer source dependencies

## NapCat

`napcat-source.json` records the pinned source and existing runtime-archive hashes.
The original project is [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ);
the historical source/tag archive is [XingYunStar/NapCatQQ](https://github.com/XingYunStar/NapCatQQ).

The optional `modules/napcat-for-self/` directory (not shipped in this repository) is
an **independent maintainer Git checkout**, not
a runtime directory, not a registered submodule, and not included in Bot packages.
The outer repository records this metadata rather than silently staging an
embedded repository or publishing its history. Current product installation does
not read this checkout. Existing NapCat configuration and login data must not be
copied here.

The initial source baseline is `v4.18.38` /
`bbd0d2aca3d470c20b33b1d4f95123335633bf26`, matching the version pinned in
`application.toml`. Merely switching this checkout to another tag does **not**
upgrade the product runtime.

### Maintenance boundaries

1. Work on an explicit maintenance/fix branch; preserve historical tags and the
   separate offline archive. Review a third-party fork's diff before taking code.
2. Preserve NapCat's original `LICENSE` and attribution. Its license is separate
   from Bot's license; public modified redistribution needs its own review.
3. Use the selected source version's build instructions and lockfile. Review
   dependency lifecycle scripts and do not run upstream publication workflows
   with deployment credentials.
4. Test and build in isolated directories. Review native binary provenance as
   well as JavaScript/TypeScript: several native implementation sources are not
   included, so this is not a claim of a fully reproducible native build.
5. Only after validation, update the source pin, archive URLs/hashes in
   `application.toml`, applicable notices, and rebuilt portable manifests/packages
   together. Keep an explicitly tested rollback package. Publication and real QQ
   acceptance are separate operations, never consequences of a source checkout.

This layout is local source integration, not a new public fork or a change to the
product's OneBot/NapCat runtime.

Maintainer agent instructions live at `modules/napcat-for-self/AGENTS.md` locally;
the source checkout and host-specific instructions are not automatically published
with the outer Bot repository. `third_party/` holds metadata, not a second source copy.
