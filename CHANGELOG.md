# Changelog

## [1.4.0](https://github.com/chattersley/sunsynk-home-assistant/compare/v1.3.0...v1.4.0) (2026-04-22)


### Features

* add writable Battery Max Discharge Current number entity ([417aa0d](https://github.com/chattersley/sunsynk-home-assistant/commit/417aa0d614e73a527563298cdd59246753df2ab1)), closes [#18](https://github.com/chattersley/sunsynk-home-assistant/issues/18)


### Bug Fixes

* correct invalid except clause syntax in number platform ([d3e9b27](https://github.com/chattersley/sunsynk-home-assistant/commit/d3e9b27e8ffbb57759309d0568e38c5031673041))
* read installed PV capacity from plant detail, not list item ([34661b7](https://github.com/chattersley/sunsynk-home-assistant/commit/34661b7a76bb35c4971b950794e2bd6c5af1a0f6)), closes [#15](https://github.com/chattersley/sunsynk-home-assistant/issues/15)
* send full programme state on every timer write ([69867c9](https://github.com/chattersley/sunsynk-home-assistant/commit/69867c9f4f733a5f56e0e42fcf80b064993ef34a)), closes [#16](https://github.com/chattersley/sunsynk-home-assistant/issues/16)
* triage open issues ([#15](https://github.com/chattersley/sunsynk-home-assistant/issues/15), [#16](https://github.com/chattersley/sunsynk-home-assistant/issues/16), [#18](https://github.com/chattersley/sunsynk-home-assistant/issues/18), partial [#9](https://github.com/chattersley/sunsynk-home-assistant/issues/9)) ([f0031c5](https://github.com/chattersley/sunsynk-home-assistant/commit/f0031c5a8880015cf5615c91114674198b896470))

## [1.3.0](https://github.com/chattersley/sunsynk-home-assistant/compare/v1.2.2...v1.3.0) (2026-04-21)


### Features

* add grid trickle feed (zero export power) number entity ([#2](https://github.com/chattersley/sunsynk-home-assistant/issues/2)) ([a6b0339](https://github.com/chattersley/sunsynk-home-assistant/commit/a6b033902bb22212cf8d60a6ed8856e2bd70e6bd))
* add installed PV capacity sensor ([#3](https://github.com/chattersley/sunsynk-home-assistant/issues/3)) ([2525fb7](https://github.com/chattersley/sunsynk-home-assistant/commit/2525fb757a6583f8638a58d48c747341b7025f65))
* add per-slot Sell switches using SDK 0.3.0 ([6cc661b](https://github.com/chattersley/sunsynk-home-assistant/commit/6cc661bffe22896ad69d12639a39e55695f93169))
* add per-slot Sell switches using sunsynk-python 0.3.0 ([e16b973](https://github.com/chattersley/sunsynk-home-assistant/commit/e16b973a17b2389902107e59ba30df9fa0a94407))
* render status codes as enum sensors ([#4](https://github.com/chattersley/sunsynk-home-assistant/issues/4)) ([0bcbc91](https://github.com/chattersley/sunsynk-home-assistant/commit/0bcbc9101a5431d405b65f90f0e65d5ea12b095f))
* vendor openapi spec v1.2.0 and resolve issues [#1](https://github.com/chattersley/sunsynk-home-assistant/issues/1)–[#4](https://github.com/chattersley/sunsynk-home-assistant/issues/4) ([3387fa9](https://github.com/chattersley/sunsynk-home-assistant/commit/3387fa97c54cfd77090a9ecfc3d18fd3602c95db))


### Bug Fixes

* correct sys_work_mode labels to match SunSynk portal ([739e018](https://github.com/chattersley/sunsynk-home-assistant/commit/739e018320893e1e0c6fa0fb00fe390b2baf031c))
* correct sys_work_mode labels to match SunSynk portal ([c32df61](https://github.com/chattersley/sunsynk-home-assistant/commit/c32df611eeb8c31ed483210e17481ebb9fb70494))
* map zeroExportPower to snake_case for SDK setter ([5f8c162](https://github.com/chattersley/sunsynk-home-assistant/commit/5f8c162509d126b59584542e7c1b5527b18f4195))
* map zeroExportPower to snake_case for SDK setter ([acafa4e](https://github.com/chattersley/sunsynk-home-assistant/commit/acafa4ecaa322d3c79bcf6d86027ec5f8e28e77d)), closes [#10](https://github.com/chattersley/sunsynk-home-assistant/issues/10)
* power unit scaling on inverter sensors ([#1](https://github.com/chattersley/sunsynk-home-assistant/issues/1)) ([d2adfc7](https://github.com/chattersley/sunsynk-home-assistant/commit/d2adfc731357fa79778529d863f6dfee480e483e))
