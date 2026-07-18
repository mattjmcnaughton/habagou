# [1.7.0](https://github.com/mattjmcnaughton/habagou/compare/v1.6.1...v1.7.0) (2026-07-18)


### Features

* **packs:** add user-scoped pack deletion end to end ([#110](https://github.com/mattjmcnaughton/habagou/issues/110)) ([3a91dda](https://github.com/mattjmcnaughton/habagou/commit/3a91ddacb683c748d1b295e456b1c3a1a3df0441))

## [1.6.1](https://github.com/mattjmcnaughton/habagou/compare/v1.6.0...v1.6.1) (2026-07-17)


### Performance Improvements

* **generation:** front-load the traceable corpus into the agent prompt ([75d0846](https://github.com/mattjmcnaughton/habagou/commit/75d08468f0db79e9559294ba04e2e31e11407b16))

# [1.6.0](https://github.com/mattjmcnaughton/habagou/compare/v1.5.0...v1.6.0) (2026-07-17)


### Features

* **generation:** add AI pack creation and observability ([65497cd](https://github.com/mattjmcnaughton/habagou/commit/65497cd69782d51d57b31dfdb3bed34c37927068)), closes [#102](https://github.com/mattjmcnaughton/habagou/issues/102) [#106](https://github.com/mattjmcnaughton/habagou/issues/106)

# [1.5.0](https://github.com/mattjmcnaughton/habagou/compare/v1.4.0...v1.5.0) (2026-07-16)


### Bug Fixes

* **packs:** corpus-validate sentence glyphs in pack create ([efd1dd6](https://github.com/mattjmcnaughton/habagou/commit/efd1dd6738dd9facce430d59157ec2dd817e881c))


### Features

* **api:** add pack generation draft endpoint ([b305bbe](https://github.com/mattjmcnaughton/habagou/commit/b305bbe060441a83a5c210401354b9892de1ff36))
* **api:** add pack generation save endpoint ([ff1a4ba](https://github.com/mattjmcnaughton/habagou/commit/ff1a4ba8dccc615665937a8f14f9ec71c8ecad85))
* **api:** rate limit generation and emit WF-15 events ([2edbbbc](https://github.com/mattjmcnaughton/habagou/commit/2edbbbc7535705dbdd0253271df5e764b090ff62))
* **config:** add generation provider settings ([ddc40b4](https://github.com/mattjmcnaughton/habagou/commit/ddc40b4287d33b69eafbd44d09687b3a1b2a94c5))
* **deps:** add pydantic-ai for agent pack generation ([68d3069](https://github.com/mattjmcnaughton/habagou/commit/68d306970e9337f33aacc14dbb44ff3b977bb3c8))
* **dtos:** add PackDraft generation output schema ([77b8ebb](https://github.com/mattjmcnaughton/habagou/commit/77b8ebb5fa537b17c48525a320145b7e8206163d))
* **generation:** add find_characters grounding tool ([65141cd](https://github.com/mattjmcnaughton/habagou/commit/65141cd0462ec51c2dbb38e2b5f4bc1d878210cf))
* **generation:** add generation service with injected agent ([1e28eec](https://github.com/mattjmcnaughton/habagou/commit/1e28eecd45b9039c93cb20a85315967e59503088))
* **generation:** reject non-corpus hanzi in agent output ([78d0528](https://github.com/mattjmcnaughton/habagou/commit/78d0528c38d2415c45e26948a4929cc160a80e62))
* **generation:** thread multi-turn message history ([7d6f4eb](https://github.com/mattjmcnaughton/habagou/commit/7d6f4ebed08bf2d6a26b6bf668578e2f9bc519bf))

# [1.4.0](https://github.com/mattjmcnaughton/habagou/compare/v1.3.0...v1.4.0) (2026-07-13)


### Features

* **packs:** add Pack.owner_id ownership column ([804349d](https://github.com/mattjmcnaughton/habagou/commit/804349d4bd61ea24e1cf8c79e75658794471da56)), closes [#88](https://github.com/mattjmcnaughton/habagou/issues/88)
* **packs:** add PackRepository.create write path for owned packs ([e44f3c7](https://github.com/mattjmcnaughton/habagou/commit/e44f3c794f946fbd667d772fcab6210d6a25a45f)), closes [#89](https://github.com/mattjmcnaughton/habagou/issues/89)
* **packs:** address packs by id in the repository ([4e57ce5](https://github.com/mattjmcnaughton/habagou/commit/4e57ce511bada7fa0178cd3748460d7ce22a2e88)), closes [#93](https://github.com/mattjmcnaughton/habagou/issues/93)

# [1.3.0](https://github.com/mattjmcnaughton/habagou/compare/v1.2.0...v1.3.0) (2026-07-13)


### Features

* **path:** add the Learning Path — spaced-repetition three-tab app ([7c3d64c](https://github.com/mattjmcnaughton/habagou/commit/7c3d64c61af7165e8e0d54f673d903e2d78d88e2))

# [1.2.0](https://github.com/mattjmcnaughton/habagou/compare/v1.1.2...v1.2.0) (2026-07-12)


### Features

* **auth:** add Keycloak OIDC login ([bc3e2d0](https://github.com/mattjmcnaughton/habagou/commit/bc3e2d0361bbf1f239ba238d5913a9b7d0df0763))
* **auth:** configure OIDC deployment ([9680552](https://github.com/mattjmcnaughton/habagou/commit/9680552fda9cee8bc0184a51a99e13e0dc911785))
* **auth:** support configurable OIDC providers ([6bf52a0](https://github.com/mattjmcnaughton/habagou/commit/6bf52a0662122a0ebb64b00fc80ec6b3aa52a827))

## [1.1.2](https://github.com/mattjmcnaughton/habagou/compare/v1.1.1...v1.1.2) (2026-07-05)


### Bug Fixes

* correct stale Kubernetes deployment note in README ([3512855](https://github.com/mattjmcnaughton/habagou/commit/35128553477755b59d445fe0b48f8ea61d415376))

## [1.1.1](https://github.com/mattjmcnaughton/habagou/compare/v1.1.0...v1.1.1) (2026-07-05)


### Bug Fixes

* **match:** add tile selection and match feedback ([3d5d8b2](https://github.com/mattjmcnaughton/habagou/commit/3d5d8b25821c9d06d0722d75c34a9c95724f8611))

# [1.1.0](https://github.com/mattjmcnaughton/habagou/compare/v1.0.1...v1.1.0) (2026-07-05)


### Features

* **progress:** add progress dashboard ([1e0f26e](https://github.com/mattjmcnaughton/habagou/commit/1e0f26ed8868efd7fae934c0df281de09195bb02))

## [1.0.1](https://github.com/mattjmcnaughton/habagou/compare/v1.0.0...v1.0.1) (2026-07-05)


### Bug Fixes

* **helm:** add host rule to ingress ([68c1e8d](https://github.com/mattjmcnaughton/habagou/commit/68c1e8de1d76230e81f160c252ff974937699c60))

# 1.0.0 (2026-07-05)


### Bug Fixes

* keep trace writer alive across progress updates ([097fa94](https://github.com/mattjmcnaughton/habagou/commit/097fa94819cd77b8a94a42a384853a9f5c2aca6f))


### Features

* **api:** add admin pack endpoints ([1f0316b](https://github.com/mattjmcnaughton/habagou/commit/1f0316baf9d570c2337f000c0f7077639596176c)), closes [#14](https://github.com/mattjmcnaughton/habagou/issues/14)
* **api:** add character strokes endpoint ([02923cb](https://github.com/mattjmcnaughton/habagou/commit/02923cb2cc4c868a1e1d5087ec6c54cd12470387)), closes [#12](https://github.com/mattjmcnaughton/habagou/issues/12)
* **api:** add current user dependency and workflow events ([c840ad6](https://github.com/mattjmcnaughton/habagou/commit/c840ad61fe0120ad717ffd60db17550a7d9d832a)), closes [#10](https://github.com/mattjmcnaughton/habagou/issues/10)
* **api:** add packs endpoints ([6bcaca4](https://github.com/mattjmcnaughton/habagou/commit/6bcaca4b28cc07a2138acd58606222f016dbd298)), closes [#11](https://github.com/mattjmcnaughton/habagou/issues/11)
* **api:** add progress endpoints ([c376c6c](https://github.com/mattjmcnaughton/habagou/commit/c376c6c5992949adad26ae7889db875b4d77731c)), closes [#13](https://github.com/mattjmcnaughton/habagou/issues/13)
* **api:** generate frontend OpenAPI contract types ([7404a13](https://github.com/mattjmcnaughton/habagou/commit/7404a13e79db3f251aab767226b785650548bdfd)), closes [#15](https://github.com/mattjmcnaughton/habagou/issues/15)
* **data:** import hanzi writer stroke corpus ([da089da](https://github.com/mattjmcnaughton/habagou/commit/da089da41aa885b7677e09eadb6bb0a6ca3b0f9c))
* **db:** add initial application schema ([747446b](https://github.com/mattjmcnaughton/habagou/commit/747446b77540aefc9bd3828a4795244f9b36860e))
* **frontend:** add app shell and design tokens ([90d5bd3](https://github.com/mattjmcnaughton/habagou/commit/90d5bd30e6ca4941612dd5aef1598ec1150d80ac)), closes [#16](https://github.com/mattjmcnaughton/habagou/issues/16)
* **frontend:** add home and pack screens ([100d6ce](https://github.com/mattjmcnaughton/habagou/commit/100d6ce721c55116d60ce92be3af9d6449d3c076)), closes [#17](https://github.com/mattjmcnaughton/habagou/issues/17)
* **frontend:** add match activity ([813ab14](https://github.com/mattjmcnaughton/habagou/commit/813ab143071373b2efadad284fa8f17d5ab92e1d)), closes [#20](https://github.com/mattjmcnaughton/habagou/issues/20)
* **frontend:** add sentence activity ([1414670](https://github.com/mattjmcnaughton/habagou/commit/141467051c9a69f9d837af0aa734de0ba42e68ee)), closes [#21](https://github.com/mattjmcnaughton/habagou/issues/21)
* **frontend:** add trace activity ([fedcce8](https://github.com/mattjmcnaughton/habagou/commit/fedcce84edc7753951ff8ce89afda2fbb6f96de7)), closes [#19](https://github.com/mattjmcnaughton/habagou/issues/19)
* **frontend:** add trace canvas wrapper ([72863b9](https://github.com/mattjmcnaughton/habagou/commit/72863b9794ff2679ed7a3fff6a82eb9910988ea6)), closes [#18](https://github.com/mattjmcnaughton/habagou/issues/18)
* **helm:** add Habagou deployment chart ([807dd71](https://github.com/mattjmcnaughton/habagou/commit/807dd718cf5ff0cedda751d36420299b03e9ec29))
* **observability:** harden API errors and workflow events ([c6f1afd](https://github.com/mattjmcnaughton/habagou/commit/c6f1afddde5a3427b0e0c410215b7e3ce5a1d59f)), closes [#23](https://github.com/mattjmcnaughton/habagou/issues/23)
* **repositories:** add data access layer ([b46032b](https://github.com/mattjmcnaughton/habagou/commit/b46032b5f5ac55f889ae9baf5a67f6a63fc459bb)), closes [#8](https://github.com/mattjmcnaughton/habagou/issues/8)
* **seed:** add prototype data seeding ([417311b](https://github.com/mattjmcnaughton/habagou/commit/417311b609be6633ac9f40d288a851a1ad4f461f)), closes [#7](https://github.com/mattjmcnaughton/habagou/issues/7)
* **verification:** add data invariant checker ([bbe7f8d](https://github.com/mattjmcnaughton/habagou/commit/bbe7f8d5b91d91605871477a70c7215b228c83f6)), closes [#29](https://github.com/mattjmcnaughton/habagou/issues/29)
