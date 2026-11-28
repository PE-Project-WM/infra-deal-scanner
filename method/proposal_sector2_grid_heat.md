# Proposal (not built): sector 2 = grid and heat

Status: proposal for William's decision, 28 November 2026. Nothing here is in the code.

## The suggestion
Narrow the second sector from "energy transition" to **grid and heat**:
- heat networks (district and communal heating and cooling)
- last-mile electricity: connections, independent connection providers and independent distribution network operators
- grid-deferral batteries (storage sited to delay network reinforcement, paid under contracts with network operators)
- smart-grid software (flexibility platforms, network monitoring)

## Why it fits the method
- **Brownfield and contracted or regulated.** Heat networks became a regulated utility on 27 January 2026: Ofgem now authorises operators and existing networks must register by 26 January 2027. Independent distribution networks are already Ofgem-licensed. That makes the infrastructure test (revenue type, contract length, inflation linkage) more informative than in digital, where most companies came out merchant.
- **Investor appetite.** William's review of the investor surveys points to rising UK appetite in grid and heat, while generation-led energy transition is more crowded and more exposed to power prices. Heat network zoning in England (the government response was published on 21 January 2026; regulations are still being drafted) would give designated networks a protected area to grow in.
- **Same machinery.** The business types carry over: network owner (heat network or distribution network operator), recurring services (metering and billing, operation and maintenance), contractor (connections and installation), project company (a single contracted asset).

## What would change
- Settings file `config/thesis/grid_heat.json`: industry codes (35300 steam and air conditioning supply, 35130 and 35140 electricity distribution and trade, 42220 utility projects for electricity, 43210 electrical installation, plus software codes for the smart-grid part), size band, business-type defaults, price ranges and hurdle rates for regulated and contracted assets.
- Sector measures: homes and buildings connected, MW of heat, connections delivered, MWh of storage under contract.
- Deal history: logged deals of the last three years in the sector, before the weights are trusted.

## Candidates already flagged in the digital run
- **James Fisher Renewables**: high-voltage and blade services to renewables. Its high-voltage work fits last-mile electricity; check how much is generation-side.
- **Evero Energy**: a biomass holding company. Generation, so outside a narrow grid-and-heat scope unless its plants sell heat under contract.
- **Sumando**: solar design, installation and maintenance. Belongs with a solar sector, not grid and heat.

## Open questions for William
1. Include smart-grid software, or keep the sector to physical assets and the services around them?
2. Are grid-deferral batteries in, given that much of their revenue can be merchant (trading) rather than contracted?
3. Keep solar as its own later sector (Sumando and others), or fold it into energy transition as a third sector?
