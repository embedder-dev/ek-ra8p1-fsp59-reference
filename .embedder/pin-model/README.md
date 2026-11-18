# RA8P1 pin model

Renesas's official RA8P1 pin model, copied unchanged from the FSP 6.0.0 MCU pack
`Renesas.RA_mcu_ra8p1.6.0.0.pack` (`.mcu/.pinmapping` and `.mcu/.pinconfig`).

- `pinmapping/`: `PinCfgR7KA8P1<variant>xxCA{B,C}.xml` per part group and package, plus `pluginra8p1.xml`.
- `pinconfig/`: one `<part>.pincfg` per orderable part.

EK-RA8P1 uses `R7KA8P1KFLCAC` (BGA289): `pinmapping/PinCfgR7KA8P1KxxCAC.xml` and `pinconfig/R7KA8P1KFLCAC.pincfg`.

Use it as given. Take pin ids from it; don't edit, rename or extend it.
