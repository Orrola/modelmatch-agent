"""Explicit per-ID product-label review of a retained AA snapshot; no name inference."""

REVIEW_DATE = "2026-11-17"

# Fixed reviewed membership, never a pattern-based grouping rule.
REVIEWED_GROUPS = ({'family_id': 'google:gemini-4-carbon:r2026-10-28',
  'label': 'Gemini 4 Carbon',
  'product_version': '4 Carbon',
  'release_date': '2026-10-28',
  'size_label': None,
  'routing_label': None,
  'members': [{'model_id': '909ed0ba-bcc5-4f38-8162-08a4e187a772',
               'identity': {'name': 'Gemini 4 Carbon (High)',
                            'slug': 'gemini-4-carbon',
                            'release_date': '2026-10-28',
                            'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                            'creator_name': 'Google'},
               'reasoning_label': 'High'},
              {'model_id': '0d3eaafd-54ed-4f78-bdd7-05a2db883986',
               'identity': {'name': 'Gemini 4 Carbon (Medium)',
                            'slug': 'gemini-4-carbon-medium',
                            'release_date': '2026-10-28',
                            'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                            'creator_name': 'Google'},
               'reasoning_label': 'Medium'},
              {'model_id': 'b3866703-a9f7-4ea2-8f3f-b361c90aaf0e',
               'identity': {'name': 'Gemini 4 Carbon (Low)',
                            'slug': 'gemini-4-carbon-low',
                            'release_date': '2026-10-28',
                            'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                            'creator_name': 'Google'},
               'reasoning_label': 'Low'}],
  'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. No routing identity is asserted where the AA label does not '
               'state one. The enumerated entries share this AA product label and release; configurations stay '
               'distinct. Different product versions, releases, sizes, Preview, quantization and routes are not '
               'automatically included. This is curated product grouping, not verified identical weights, '
               'deployment or provider equivalence.'},
 {'family_id': 'anthropic:claude-opus-5.5:default-fallback:r2026-09-22',
  'label': 'Claude Opus 5.5',
  'product_version': '5.5',
  'release_date': '2026-09-22',
  'size_label': None,
  'routing_label': 'Default Fallback',
  'members': [{'model_id': '2f3c4dc9-a450-4303-8697-0237257cf08f',
               'identity': {'name': 'Claude Opus 5.5 (Max, Default Fallback)',
                            'slug': 'claude-opus-5-5',
                            'release_date': '2026-09-22',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'Max'},
              {'model_id': 'df5bf99d-d228-4715-b41b-19ca86118777',
               'identity': {'name': 'Claude Opus 5.5 (Xhigh, Default Fallback)',
                            'slug': 'claude-opus-5-5-xhigh',
                            'release_date': '2026-09-22',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'Xhigh'},
              {'model_id': 'f314eade-2232-44bf-a3ab-9b326bc67de6',
               'identity': {'name': 'Claude Opus 5.5 (High, Default Fallback)',
                            'slug': 'claude-opus-5-5-high',
                            'release_date': '2026-09-22',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'High'}],
  'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. Only the explicitly labeled Default Fallback route is included. '
               'The enumerated entries share this AA product label and release; configurations stay distinct. '
               'Different product versions, releases, sizes, Preview, quantization and routes are not '
               'automatically included. This is curated product grouping, not verified identical weights, '
               'deployment or provider equivalence.'},
 {'family_id': 'openai:gpt-6-astra:r2026-09-03',
  'label': 'GPT-6 Astra',
  'product_version': '6 Astra',
  'release_date': '2026-09-03',
  'size_label': None,
  'routing_label': None,
  'members': [{'model_id': '2f339a97-9a0d-499a-9cb5-e0db665bfa25',
               'identity': {'name': 'GPT-6 Astra (Max)',
                            'slug': 'gpt-6-astra',
                            'release_date': '2026-09-03',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Max'},
              {'model_id': '1f541ef3-913f-4eb2-9d07-0e93c7a9a5e3',
               'identity': {'name': 'GPT-6 Astra (Xhigh)',
                            'slug': 'gpt-6-astra-xhigh',
                            'release_date': '2026-09-03',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Xhigh'},
              {'model_id': 'e05a4828-0536-4876-870d-a235023f992b',
               'identity': {'name': 'GPT-6 Astra (High)',
                            'slug': 'gpt-6-astra-high',
                            'release_date': '2026-09-03',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'High'},
              {'model_id': 'e97a4ef5-e817-480e-9595-12f81dc4974f',
               'identity': {'name': 'GPT-6 Astra (Medium)',
                            'slug': 'gpt-6-astra-medium',
                            'release_date': '2026-09-03',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Medium'}],
  'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. No routing identity is asserted where the AA label does not '
               'state one. The enumerated entries share this AA product label and release; configurations stay '
               'distinct. Different product versions, releases, sizes, Preview, quantization and routes are not '
               'automatically included. This is curated product grouping, not verified identical weights, '
               'deployment or provider equivalence.'},
 {'family_id': 'openai:gpt-6.1-sol:r2026-09-29',
  'label': 'GPT-6.1 Sol',
  'product_version': '6.1 Sol',
  'release_date': '2026-09-29',
  'size_label': None,
  'routing_label': None,
  'members': [{'model_id': 'b25ac058-1e33-4c31-bbc9-a20c3ad0717a',
               'identity': {'name': 'GPT-6.1 Sol (Max)',
                            'slug': 'gpt-6-1-sol',
                            'release_date': '2026-09-29',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Max'},
              {'model_id': '092a3b0e-c5c8-45dc-bf1b-53673c8ff352',
               'identity': {'name': 'GPT-6.1 Sol (Xhigh)',
                            'slug': 'gpt-6-1-sol-xhigh',
                            'release_date': '2026-09-29',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Xhigh'}],
  'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. No routing identity is asserted where the AA label does not '
               'state one. The enumerated entries share this AA product label and release; configurations stay '
               'distinct. Different product versions, releases, sizes, Preview, quantization and routes are not '
               'automatically included. This is curated product grouping, not verified identical weights, '
               'deployment or provider equivalence.'},
 {'family_id': 'anthropic:claude-sonnet-5.5:default-fallback:r2026-09-28',
  'label': 'Claude Sonnet 5.5',
  'product_version': '5.5',
  'release_date': '2026-09-28',
  'size_label': None,
  'routing_label': 'Default Fallback',
  'members': [{'model_id': 'b171d979-5ec1-45de-b8b9-db1ee65e77ec',
               'identity': {'name': 'Claude Sonnet 5.5 (Max, Default Fallback)',
                            'slug': 'claude-sonnet-5-5',
                            'release_date': '2026-09-28',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'Max'}],
  'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. Only the explicitly labeled Default Fallback route is included. '
               'Single reviewed product entry; this asserts its exact labeled identity, not relationships to '
               'unreviewed variants. Different product versions, releases, sizes, Preview, quantization and '
               'routes are not automatically included. This is curated product grouping, not verified identical '
               'weights, deployment or provider equivalence.'},
 {'family_id': 'google:gemini-4-argon:r2026-09-30',
  'label': 'Gemini 4 Argon',
  'product_version': '4 Argon',
  'release_date': '2026-09-30',
  'size_label': None,
  'routing_label': None,
  'members': [{'model_id': 'd366dfa1-d940-4788-aa73-d298c45699b3',
               'identity': {'name': 'Gemini 4 Argon (High)',
                            'slug': 'gemini-4-argon',
                            'release_date': '2026-09-30',
                            'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                            'creator_name': 'Google'},
               'reasoning_label': 'High'}],
  'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. No routing identity is asserted where the AA label does not '
               'state one. Single reviewed product entry; this asserts its exact labeled identity, not '
               'relationships to unreviewed variants. Different product versions, releases, sizes, Preview, '
               'quantization and routes are not automatically included. This is curated product grouping, not '
               'verified identical weights, deployment or provider equivalence.'},
 {'family_id': 'meta:muse-wonder-full:r2026-10-12',
  'label': 'Muse Wonder Full',
  'product_version': 'Wonder Full',
  'release_date': '2026-10-12',
  'size_label': 'Full',
  'routing_label': None,
  'members': [{'model_id': 'e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2',
               'identity': {'name': 'Muse Wonder Full (Max)',
                            'slug': 'muse-wonder-full',
                            'release_date': '2026-10-12',
                            'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
                            'creator_name': 'Meta'},
               'reasoning_label': 'Max'}],
  'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. Only this exact Full size label is included. No routing identity '
               'is asserted where the AA label does not state one. Single reviewed product entry; this asserts '
               'its exact labeled identity, not relationships to unreviewed variants. Different product versions, '
               'releases, sizes, Preview, quantization and routes are not automatically included. This is curated '
               'product grouping, not verified identical weights, deployment or provider equivalence.'},
 {'family_id': 'anthropic:claude-fable-5.1:default-fallback:r2026-09-01',
  'label': 'Claude Fable 5.1',
  'product_version': '5.1',
  'release_date': '2026-09-01',
  'size_label': None,
  'routing_label': 'Default Fallback',
  'members': [{'model_id': '3e87c73e-a257-495e-9730-367a66229811',
               'identity': {'name': 'Claude Fable 5.1 (Max, Default Fallback)',
                            'slug': 'claude-fable-5-1',
                            'release_date': '2026-09-01',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'Max'},
              {'model_id': '9b166bf3-42db-4f63-8338-1c4a1244ffe8',
               'identity': {'name': 'Claude Fable 5.1 (Xhigh, Default Fallback)',
                            'slug': 'claude-fable-5-1-xhigh',
                            'release_date': '2026-09-01',
                            'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                            'creator_name': 'Anthropic'},
               'reasoning_label': 'Xhigh'}],
  'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. Only the explicitly labeled Default Fallback route is included. '
               'The enumerated entries share this AA product label and release; configurations stay distinct. '
               'Different product versions, releases, sizes, Preview, quantization and routes are not '
               'automatically included. This is curated product grouping, not verified identical weights, '
               'deployment or provider equivalence.'},
 {'family_id': 'openai:gpt-6.1-terra:r2026-10-26',
  'label': 'GPT-6.1 Terra',
  'product_version': '6.1 Terra',
  'release_date': '2026-10-26',
  'size_label': None,
  'routing_label': None,
  'members': [{'model_id': 'b0c462cf-f2d0-4126-9434-28db9502219f',
               'identity': {'name': 'GPT-6.1 Terra (Max)',
                            'slug': 'gpt-6-1-terra',
                            'release_date': '2026-10-26',
                            'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                            'creator_name': 'OpenAI'},
               'reasoning_label': 'Max'}],
  'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
  'rationale': 'Explicit review of the exact AA IDs, creator, complete product/version labels, release date and '
               'listed reasoning configurations. No routing identity is asserted where the AA label does not '
               'state one. Single reviewed product entry; this asserts its exact labeled identity, not '
               'relationships to unreviewed variants. Different product versions, releases, sizes, Preview, '
               'quantization and routes are not automatically included. This is curated product grouping, not '
               'verified identical weights, deployment or provider equivalence.'})
