"""Independent identity-only manifest for the explicitly revalidated AA snapshot."""

REVALIDATED_MAPPING = {'version': 'aa-label-families-v3',
 'families': {'anthropic:claude-fable-5.2': {'label': 'Claude Fable 5.2',
                                             'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                             'grouping_confidence': 'curated_aa_label',
                                             'provider_equivalence_status': 'unknown',
                                             'product_version': '5.2',
                                             'release_date': '2026-11-09',
                                             'size_label': None,
                                             'routing_label': 'Default Fallback',
                                             'review_status': 'reviewed_aa_product_label_only'},
              'google:gemini-4-carbon:r2026-10-28': {'label': 'Gemini 4 Carbon',
                                                     'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                     'product_version': '4 Carbon',
                                                     'release_date': '2026-10-28',
                                                     'size_label': None,
                                                     'routing_label': None,
                                                     'grouping_confidence': 'curated_aa_label',
                                                     'provider_equivalence_status': 'unknown',
                                                     'review_status': 'reviewed_aa_product_label_only',
                                                     'rationale': 'Explicit review of the exact AA IDs, '
                                                                  'creator, complete product/version labels, '
                                                                  'release date and listed reasoning '
                                                                  'configurations. No routing identity is '
                                                                  'asserted where the AA label does not '
                                                                  'state one. The enumerated entries share '
                                                                  'this AA product label and release; '
                                                                  'configurations stay distinct. Different '
                                                                  'product versions, releases, sizes, '
                                                                  'Preview, quantization and routes are not '
                                                                  'automatically included. This is curated '
                                                                  'product grouping, not verified identical '
                                                                  'weights, deployment or provider '
                                                                  'equivalence.'},
              'anthropic:claude-opus-5.5:default-fallback:r2026-09-22': {'label': 'Claude Opus 5.5',
                                                                         'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                                         'product_version': '5.5',
                                                                         'release_date': '2026-09-22',
                                                                         'size_label': None,
                                                                         'routing_label': 'Default Fallback',
                                                                         'grouping_confidence': 'curated_aa_label',
                                                                         'provider_equivalence_status': 'unknown',
                                                                         'review_status': 'reviewed_aa_product_label_only',
                                                                         'rationale': 'Explicit review of '
                                                                                      'the exact AA IDs, '
                                                                                      'creator, complete '
                                                                                      'product/version '
                                                                                      'labels, release date '
                                                                                      'and listed reasoning '
                                                                                      'configurations. Only '
                                                                                      'the explicitly '
                                                                                      'labeled Default '
                                                                                      'Fallback route is '
                                                                                      'included. The '
                                                                                      'enumerated entries '
                                                                                      'share this AA product '
                                                                                      'label and release; '
                                                                                      'configurations stay '
                                                                                      'distinct. Different '
                                                                                      'product versions, '
                                                                                      'releases, sizes, '
                                                                                      'Preview, quantization '
                                                                                      'and routes are not '
                                                                                      'automatically '
                                                                                      'included. This is '
                                                                                      'curated product '
                                                                                      'grouping, not '
                                                                                      'verified identical '
                                                                                      'weights, deployment '
                                                                                      'or provider '
                                                                                      'equivalence.'},
              'openai:gpt-6-astra:r2026-09-03': {'label': 'GPT-6 Astra',
                                                 'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                 'product_version': '6 Astra',
                                                 'release_date': '2026-09-03',
                                                 'size_label': None,
                                                 'routing_label': None,
                                                 'grouping_confidence': 'curated_aa_label',
                                                 'provider_equivalence_status': 'unknown',
                                                 'review_status': 'reviewed_aa_product_label_only',
                                                 'rationale': 'Explicit review of the exact AA IDs, creator, '
                                                              'complete product/version labels, release date '
                                                              'and listed reasoning configurations. No '
                                                              'routing identity is asserted where the AA '
                                                              'label does not state one. The enumerated '
                                                              'entries share this AA product label and '
                                                              'release; configurations stay distinct. '
                                                              'Different product versions, releases, sizes, '
                                                              'Preview, quantization and routes are not '
                                                              'automatically included. This is curated '
                                                              'product grouping, not verified identical '
                                                              'weights, deployment or provider equivalence.'},
              'openai:gpt-6.1-sol:r2026-09-29': {'label': 'GPT-6.1 Sol',
                                                 'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                 'product_version': '6.1 Sol',
                                                 'release_date': '2026-09-29',
                                                 'size_label': None,
                                                 'routing_label': None,
                                                 'grouping_confidence': 'curated_aa_label',
                                                 'provider_equivalence_status': 'unknown',
                                                 'review_status': 'reviewed_aa_product_label_only',
                                                 'rationale': 'Explicit review of the exact AA IDs, creator, '
                                                              'complete product/version labels, release date '
                                                              'and listed reasoning configurations. No '
                                                              'routing identity is asserted where the AA '
                                                              'label does not state one. The enumerated '
                                                              'entries share this AA product label and '
                                                              'release; configurations stay distinct. '
                                                              'Different product versions, releases, sizes, '
                                                              'Preview, quantization and routes are not '
                                                              'automatically included. This is curated '
                                                              'product grouping, not verified identical '
                                                              'weights, deployment or provider equivalence.'},
              'anthropic:claude-sonnet-5.5:default-fallback:r2026-09-28': {'label': 'Claude Sonnet 5.5',
                                                                           'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                                           'product_version': '5.5',
                                                                           'release_date': '2026-09-28',
                                                                           'size_label': None,
                                                                           'routing_label': 'Default '
                                                                                            'Fallback',
                                                                           'grouping_confidence': 'curated_aa_label',
                                                                           'provider_equivalence_status': 'unknown',
                                                                           'review_status': 'reviewed_aa_product_label_only',
                                                                           'rationale': 'Explicit review of '
                                                                                        'the exact AA IDs, '
                                                                                        'creator, complete '
                                                                                        'product/version '
                                                                                        'labels, release '
                                                                                        'date and listed '
                                                                                        'reasoning '
                                                                                        'configurations. '
                                                                                        'Only the explicitly '
                                                                                        'labeled Default '
                                                                                        'Fallback route is '
                                                                                        'included. Single '
                                                                                        'reviewed product '
                                                                                        'entry; this asserts '
                                                                                        'its exact labeled '
                                                                                        'identity, not '
                                                                                        'relationships to '
                                                                                        'unreviewed '
                                                                                        'variants. Different '
                                                                                        'product versions, '
                                                                                        'releases, sizes, '
                                                                                        'Preview, '
                                                                                        'quantization and '
                                                                                        'routes are not '
                                                                                        'automatically '
                                                                                        'included. This is '
                                                                                        'curated product '
                                                                                        'grouping, not '
                                                                                        'verified identical '
                                                                                        'weights, deployment '
                                                                                        'or provider '
                                                                                        'equivalence.'},
              'google:gemini-4-argon:r2026-09-30': {'label': 'Gemini 4 Argon',
                                                    'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                    'product_version': '4 Argon',
                                                    'release_date': '2026-09-30',
                                                    'size_label': None,
                                                    'routing_label': None,
                                                    'grouping_confidence': 'curated_aa_label',
                                                    'provider_equivalence_status': 'unknown',
                                                    'review_status': 'reviewed_aa_product_label_only',
                                                    'rationale': 'Explicit review of the exact AA IDs, '
                                                                 'creator, complete product/version labels, '
                                                                 'release date and listed reasoning '
                                                                 'configurations. No routing identity is '
                                                                 'asserted where the AA label does not state '
                                                                 'one. Single reviewed product entry; this '
                                                                 'asserts its exact labeled identity, not '
                                                                 'relationships to unreviewed variants. '
                                                                 'Different product versions, releases, '
                                                                 'sizes, Preview, quantization and routes '
                                                                 'are not automatically included. This is '
                                                                 'curated product grouping, not verified '
                                                                 'identical weights, deployment or provider '
                                                                 'equivalence.'},
              'meta:muse-wonder-full:r2026-10-12': {'label': 'Muse Wonder Full',
                                                    'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
                                                    'product_version': 'Wonder Full',
                                                    'release_date': '2026-10-12',
                                                    'size_label': 'Full',
                                                    'routing_label': None,
                                                    'grouping_confidence': 'curated_aa_label',
                                                    'provider_equivalence_status': 'unknown',
                                                    'review_status': 'reviewed_aa_product_label_only',
                                                    'rationale': 'Explicit review of the exact AA IDs, '
                                                                 'creator, complete product/version labels, '
                                                                 'release date and listed reasoning '
                                                                 'configurations. Only this exact Full size '
                                                                 'label is included. No routing identity is '
                                                                 'asserted where the AA label does not state '
                                                                 'one. Single reviewed product entry; this '
                                                                 'asserts its exact labeled identity, not '
                                                                 'relationships to unreviewed variants. '
                                                                 'Different product versions, releases, '
                                                                 'sizes, Preview, quantization and routes '
                                                                 'are not automatically included. This is '
                                                                 'curated product grouping, not verified '
                                                                 'identical weights, deployment or provider '
                                                                 'equivalence.'},
              'anthropic:claude-fable-5.1:default-fallback:r2026-09-01': {'label': 'Claude Fable 5.1',
                                                                          'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                                          'product_version': '5.1',
                                                                          'release_date': '2026-09-01',
                                                                          'size_label': None,
                                                                          'routing_label': 'Default Fallback',
                                                                          'grouping_confidence': 'curated_aa_label',
                                                                          'provider_equivalence_status': 'unknown',
                                                                          'review_status': 'reviewed_aa_product_label_only',
                                                                          'rationale': 'Explicit review of '
                                                                                       'the exact AA IDs, '
                                                                                       'creator, complete '
                                                                                       'product/version '
                                                                                       'labels, release date '
                                                                                       'and listed reasoning '
                                                                                       'configurations. Only '
                                                                                       'the explicitly '
                                                                                       'labeled Default '
                                                                                       'Fallback route is '
                                                                                       'included. The '
                                                                                       'enumerated entries '
                                                                                       'share this AA '
                                                                                       'product label and '
                                                                                       'release; '
                                                                                       'configurations stay '
                                                                                       'distinct. Different '
                                                                                       'product versions, '
                                                                                       'releases, sizes, '
                                                                                       'Preview, '
                                                                                       'quantization and '
                                                                                       'routes are not '
                                                                                       'automatically '
                                                                                       'included. This is '
                                                                                       'curated product '
                                                                                       'grouping, not '
                                                                                       'verified identical '
                                                                                       'weights, deployment '
                                                                                       'or provider '
                                                                                       'equivalence.'},
              'openai:gpt-6.1-terra:r2026-10-26': {'label': 'GPT-6.1 Terra',
                                                   'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                   'product_version': '6.1 Terra',
                                                   'release_date': '2026-10-26',
                                                   'size_label': None,
                                                   'routing_label': None,
                                                   'grouping_confidence': 'curated_aa_label',
                                                   'provider_equivalence_status': 'unknown',
                                                   'review_status': 'reviewed_aa_product_label_only',
                                                   'rationale': 'Explicit review of the exact AA IDs, '
                                                                'creator, complete product/version labels, '
                                                                'release date and listed reasoning '
                                                                'configurations. No routing identity is '
                                                                'asserted where the AA label does not state '
                                                                'one. Single reviewed product entry; this '
                                                                'asserts its exact labeled identity, not '
                                                                'relationships to unreviewed variants. '
                                                                'Different product versions, releases, '
                                                                'sizes, Preview, quantization and routes are '
                                                                'not automatically included. This is curated '
                                                                'product grouping, not verified identical '
                                                                'weights, deployment or provider '
                                                                'equivalence.'}},
 'records': [{'model_id': '092a3b0e-c5c8-45dc-bf1b-53673c8ff352',
              'family_id': 'openai:gpt-6.1-sol:r2026-09-29',
              'expected_identity': {'name': 'GPT-6.1 Sol (Xhigh)',
                                    'slug': 'gpt-6-1-sol-xhigh',
                                    'release_date': '2026-09-29',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Xhigh',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:092a3b0e-c5c8-45dc-bf1b-53673c8ff352',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '092a3b0e-c5c8-45dc-bf1b-53673c8ff352',
                                      'source_fields': {'name': 'GPT-6.1 Sol (Xhigh)',
                                                        'slug': 'gpt-6-1-sol-xhigh',
                                                        'release_date': '2026-09-29',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6.1 Sol',
                                                                     'release_date': '2026-09-29'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:092a3b0e-c5c8-45dc-bf1b-53673c8ff352',
              'release_version': {'product_version': '6.1 Sol', 'release_date': '2026-09-29'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '0c9b4e05-9259-42cc-b40e-d6acbbeaa7e8',
              'family_id': 'anthropic:claude-fable-5.2',
              'expected_identity': {'name': 'Claude Fable 5.2 (Medium, Default Fallback)',
                                    'slug': 'claude-fable-5-2-medium',
                                    'release_date': '2026-11-09',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Medium',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:0c9b4e05-9259-42cc-b40e-d6acbbeaa7e8',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_fields': {'name': 'Claude Fable 5.2 (Medium, Default Fallback)',
                                                        'slug': 'claude-fable-5-2-medium',
                                                        'release_date': '2026-11-09',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'source_model_id': '0c9b4e05-9259-42cc-b40e-d6acbbeaa7e8',
                                      'basis': 'Manual comparison of exact AA identities; shared version '
                                               'label, distinct configuration labels. No inference of '
                                               'provider routing, supported API settings or identical '
                                               'underlying weights. Exact ID, creator object, original '
                                               'name/slug and release date match the independently retained '
                                               'new snapshot. Existing product-label grouping was '
                                               're-reviewed; no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.2',
                                                                     'release_date': '2026-11-09'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:0c9b4e05-9259-42cc-b40e-d6acbbeaa7e8',
              'release_version': {'product_version': '5.2', 'release_date': '2026-11-09'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '0d3eaafd-54ed-4f78-bdd7-05a2db883986',
              'family_id': 'google:gemini-4-carbon:r2026-10-28',
              'expected_identity': {'name': 'Gemini 4 Carbon (Medium)',
                                    'slug': 'gemini-4-carbon-medium',
                                    'release_date': '2026-10-28',
                                    'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                    'creator_name': 'Google'},
              'configuration': {'reasoning_label': 'Medium',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:0d3eaafd-54ed-4f78-bdd7-05a2db883986',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '0d3eaafd-54ed-4f78-bdd7-05a2db883986',
                                      'source_fields': {'name': 'Gemini 4 Carbon (Medium)',
                                                        'slug': 'gemini-4-carbon-medium',
                                                        'release_date': '2026-10-28',
                                                        'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                        'creator_name': 'Google'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '4 Carbon',
                                                                     'release_date': '2026-10-28'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
              'configuration_key': 'aa-configuration:0d3eaafd-54ed-4f78-bdd7-05a2db883986',
              'release_version': {'product_version': '4 Carbon', 'release_date': '2026-10-28'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '1f541ef3-913f-4eb2-9d07-0e93c7a9a5e3',
              'family_id': 'openai:gpt-6-astra:r2026-09-03',
              'expected_identity': {'name': 'GPT-6 Astra (Xhigh)',
                                    'slug': 'gpt-6-astra-xhigh',
                                    'release_date': '2026-09-03',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Xhigh',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:1f541ef3-913f-4eb2-9d07-0e93c7a9a5e3',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '1f541ef3-913f-4eb2-9d07-0e93c7a9a5e3',
                                      'source_fields': {'name': 'GPT-6 Astra (Xhigh)',
                                                        'slug': 'gpt-6-astra-xhigh',
                                                        'release_date': '2026-09-03',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6 Astra',
                                                                     'release_date': '2026-09-03'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:1f541ef3-913f-4eb2-9d07-0e93c7a9a5e3',
              'release_version': {'product_version': '6 Astra', 'release_date': '2026-09-03'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '2f339a97-9a0d-499a-9cb5-e0db665bfa25',
              'family_id': 'openai:gpt-6-astra:r2026-09-03',
              'expected_identity': {'name': 'GPT-6 Astra (Max)',
                                    'slug': 'gpt-6-astra',
                                    'release_date': '2026-09-03',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:2f339a97-9a0d-499a-9cb5-e0db665bfa25',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '2f339a97-9a0d-499a-9cb5-e0db665bfa25',
                                      'source_fields': {'name': 'GPT-6 Astra (Max)',
                                                        'slug': 'gpt-6-astra',
                                                        'release_date': '2026-09-03',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6 Astra',
                                                                     'release_date': '2026-09-03'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:2f339a97-9a0d-499a-9cb5-e0db665bfa25',
              'release_version': {'product_version': '6 Astra', 'release_date': '2026-09-03'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '2f3c4dc9-a450-4303-8697-0237257cf08f',
              'family_id': 'anthropic:claude-opus-5.5:default-fallback:r2026-09-22',
              'expected_identity': {'name': 'Claude Opus 5.5 (Max, Default Fallback)',
                                    'slug': 'claude-opus-5-5',
                                    'release_date': '2026-09-22',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:2f3c4dc9-a450-4303-8697-0237257cf08f',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '2f3c4dc9-a450-4303-8697-0237257cf08f',
                                      'source_fields': {'name': 'Claude Opus 5.5 (Max, Default Fallback)',
                                                        'slug': 'claude-opus-5-5',
                                                        'release_date': '2026-09-22',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. The enumerated entries share this AA '
                                               'product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.5',
                                                                     'release_date': '2026-09-22'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:2f3c4dc9-a450-4303-8697-0237257cf08f',
              'release_version': {'product_version': '5.5', 'release_date': '2026-09-22'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '3e87c73e-a257-495e-9730-367a66229811',
              'family_id': 'anthropic:claude-fable-5.1:default-fallback:r2026-09-01',
              'expected_identity': {'name': 'Claude Fable 5.1 (Max, Default Fallback)',
                                    'slug': 'claude-fable-5-1',
                                    'release_date': '2026-09-01',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:3e87c73e-a257-495e-9730-367a66229811',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '3e87c73e-a257-495e-9730-367a66229811',
                                      'source_fields': {'name': 'Claude Fable 5.1 (Max, Default Fallback)',
                                                        'slug': 'claude-fable-5-1',
                                                        'release_date': '2026-09-01',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. The enumerated entries share this AA '
                                               'product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.1',
                                                                     'release_date': '2026-09-01'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:3e87c73e-a257-495e-9730-367a66229811',
              'release_version': {'product_version': '5.1', 'release_date': '2026-09-01'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '593f2d23-247b-41c9-a679-cebd225f0a9a',
              'family_id': 'anthropic:claude-fable-5.2',
              'expected_identity': {'name': 'Claude Fable 5.2 (Max, Default Fallback)',
                                    'slug': 'claude-fable-5-2',
                                    'release_date': '2026-11-09',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:593f2d23-247b-41c9-a679-cebd225f0a9a',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_fields': {'name': 'Claude Fable 5.2 (Max, Default Fallback)',
                                                        'slug': 'claude-fable-5-2',
                                                        'release_date': '2026-11-09',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'source_model_id': '593f2d23-247b-41c9-a679-cebd225f0a9a',
                                      'basis': 'Manual comparison of exact AA identities; shared version '
                                               'label, distinct configuration labels. No inference of '
                                               'provider routing, supported API settings or identical '
                                               'underlying weights. Exact ID, creator object, original '
                                               'name/slug and release date match the independently retained '
                                               'new snapshot. Existing product-label grouping was '
                                               're-reviewed; no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.2',
                                                                     'release_date': '2026-11-09'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:593f2d23-247b-41c9-a679-cebd225f0a9a',
              'release_version': {'product_version': '5.2', 'release_date': '2026-11-09'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '76942526-cc96-46b0-bc27-29561c53ed70',
              'family_id': 'anthropic:claude-fable-5.2',
              'expected_identity': {'name': 'Claude Fable 5.2 (Xhigh, Default Fallback)',
                                    'slug': 'claude-fable-5-2-xhigh',
                                    'release_date': '2026-11-09',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Xhigh',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:76942526-cc96-46b0-bc27-29561c53ed70',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_fields': {'name': 'Claude Fable 5.2 (Xhigh, Default Fallback)',
                                                        'slug': 'claude-fable-5-2-xhigh',
                                                        'release_date': '2026-11-09',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'source_model_id': '76942526-cc96-46b0-bc27-29561c53ed70',
                                      'basis': 'Manual comparison of exact AA identities; shared version '
                                               'label, distinct configuration labels. No inference of '
                                               'provider routing, supported API settings or identical '
                                               'underlying weights. Exact ID, creator object, original '
                                               'name/slug and release date match the independently retained '
                                               'new snapshot. Existing product-label grouping was '
                                               're-reviewed; no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.2',
                                                                     'release_date': '2026-11-09'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:76942526-cc96-46b0-bc27-29561c53ed70',
              'release_version': {'product_version': '5.2', 'release_date': '2026-11-09'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '909ed0ba-bcc5-4f38-8162-08a4e187a772',
              'family_id': 'google:gemini-4-carbon:r2026-10-28',
              'expected_identity': {'name': 'Gemini 4 Carbon (High)',
                                    'slug': 'gemini-4-carbon',
                                    'release_date': '2026-10-28',
                                    'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                    'creator_name': 'Google'},
              'configuration': {'reasoning_label': 'High',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:909ed0ba-bcc5-4f38-8162-08a4e187a772',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '909ed0ba-bcc5-4f38-8162-08a4e187a772',
                                      'source_fields': {'name': 'Gemini 4 Carbon (High)',
                                                        'slug': 'gemini-4-carbon',
                                                        'release_date': '2026-10-28',
                                                        'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                        'creator_name': 'Google'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '4 Carbon',
                                                                     'release_date': '2026-10-28'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
              'configuration_key': 'aa-configuration:909ed0ba-bcc5-4f38-8162-08a4e187a772',
              'release_version': {'product_version': '4 Carbon', 'release_date': '2026-10-28'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': '9b166bf3-42db-4f63-8338-1c4a1244ffe8',
              'family_id': 'anthropic:claude-fable-5.1:default-fallback:r2026-09-01',
              'expected_identity': {'name': 'Claude Fable 5.1 (Xhigh, Default Fallback)',
                                    'slug': 'claude-fable-5-1-xhigh',
                                    'release_date': '2026-09-01',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Xhigh',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:9b166bf3-42db-4f63-8338-1c4a1244ffe8',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': '9b166bf3-42db-4f63-8338-1c4a1244ffe8',
                                      'source_fields': {'name': 'Claude Fable 5.1 (Xhigh, Default Fallback)',
                                                        'slug': 'claude-fable-5-1-xhigh',
                                                        'release_date': '2026-09-01',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. The enumerated entries share this AA '
                                               'product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.1',
                                                                     'release_date': '2026-09-01'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:9b166bf3-42db-4f63-8338-1c4a1244ffe8',
              'release_version': {'product_version': '5.1', 'release_date': '2026-09-01'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'b0c462cf-f2d0-4126-9434-28db9502219f',
              'family_id': 'openai:gpt-6.1-terra:r2026-10-26',
              'expected_identity': {'name': 'GPT-6.1 Terra (Max)',
                                    'slug': 'gpt-6-1-terra',
                                    'release_date': '2026-10-26',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:b0c462cf-f2d0-4126-9434-28db9502219f',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'b0c462cf-f2d0-4126-9434-28db9502219f',
                                      'source_fields': {'name': 'GPT-6.1 Terra (Max)',
                                                        'slug': 'gpt-6-1-terra',
                                                        'release_date': '2026-10-26',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. Single reviewed product entry; '
                                               'this asserts its exact labeled identity, not relationships '
                                               'to unreviewed variants. Different product versions, '
                                               'releases, sizes, Preview, quantization and routes are not '
                                               'automatically included. This is curated product grouping, '
                                               'not verified identical weights, deployment or provider '
                                               'equivalence. Exact ID, creator object, original name/slug '
                                               'and release date match the independently retained new '
                                               'snapshot. Existing product-label grouping was re-reviewed; '
                                               'no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6.1 Terra',
                                                                     'release_date': '2026-10-26'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:b0c462cf-f2d0-4126-9434-28db9502219f',
              'release_version': {'product_version': '6.1 Terra', 'release_date': '2026-10-26'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'b171d979-5ec1-45de-b8b9-db1ee65e77ec',
              'family_id': 'anthropic:claude-sonnet-5.5:default-fallback:r2026-09-28',
              'expected_identity': {'name': 'Claude Sonnet 5.5 (Max, Default Fallback)',
                                    'slug': 'claude-sonnet-5-5',
                                    'release_date': '2026-09-28',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:b171d979-5ec1-45de-b8b9-db1ee65e77ec',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'b171d979-5ec1-45de-b8b9-db1ee65e77ec',
                                      'source_fields': {'name': 'Claude Sonnet 5.5 (Max, Default Fallback)',
                                                        'slug': 'claude-sonnet-5-5',
                                                        'release_date': '2026-09-28',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. Single reviewed product entry; this '
                                               'asserts its exact labeled identity, not relationships to '
                                               'unreviewed variants. Different product versions, releases, '
                                               'sizes, Preview, quantization and routes are not '
                                               'automatically included. This is curated product grouping, '
                                               'not verified identical weights, deployment or provider '
                                               'equivalence. Exact ID, creator object, original name/slug '
                                               'and release date match the independently retained new '
                                               'snapshot. Existing product-label grouping was re-reviewed; '
                                               'no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.5',
                                                                     'release_date': '2026-09-28'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:b171d979-5ec1-45de-b8b9-db1ee65e77ec',
              'release_version': {'product_version': '5.5', 'release_date': '2026-09-28'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'b25ac058-1e33-4c31-bbc9-a20c3ad0717a',
              'family_id': 'openai:gpt-6.1-sol:r2026-09-29',
              'expected_identity': {'name': 'GPT-6.1 Sol (Max)',
                                    'slug': 'gpt-6-1-sol',
                                    'release_date': '2026-09-29',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:b25ac058-1e33-4c31-bbc9-a20c3ad0717a',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'b25ac058-1e33-4c31-bbc9-a20c3ad0717a',
                                      'source_fields': {'name': 'GPT-6.1 Sol (Max)',
                                                        'slug': 'gpt-6-1-sol',
                                                        'release_date': '2026-09-29',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6.1 Sol',
                                                                     'release_date': '2026-09-29'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:b25ac058-1e33-4c31-bbc9-a20c3ad0717a',
              'release_version': {'product_version': '6.1 Sol', 'release_date': '2026-09-29'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'b3866703-a9f7-4ea2-8f3f-b361c90aaf0e',
              'family_id': 'google:gemini-4-carbon:r2026-10-28',
              'expected_identity': {'name': 'Gemini 4 Carbon (Low)',
                                    'slug': 'gemini-4-carbon-low',
                                    'release_date': '2026-10-28',
                                    'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                    'creator_name': 'Google'},
              'configuration': {'reasoning_label': 'Low',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:b3866703-a9f7-4ea2-8f3f-b361c90aaf0e',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'b3866703-a9f7-4ea2-8f3f-b361c90aaf0e',
                                      'source_fields': {'name': 'Gemini 4 Carbon (Low)',
                                                        'slug': 'gemini-4-carbon-low',
                                                        'release_date': '2026-10-28',
                                                        'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                        'creator_name': 'Google'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '4 Carbon',
                                                                     'release_date': '2026-10-28'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
              'configuration_key': 'aa-configuration:b3866703-a9f7-4ea2-8f3f-b361c90aaf0e',
              'release_version': {'product_version': '4 Carbon', 'release_date': '2026-10-28'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'cfc7acb1-d903-4858-9b6c-6c7776caf8f9',
              'family_id': 'anthropic:claude-fable-5.2',
              'expected_identity': {'name': 'Claude Fable 5.2 (Low, Default Fallback)',
                                    'slug': 'claude-fable-5-2-low',
                                    'release_date': '2026-11-09',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Low',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:cfc7acb1-d903-4858-9b6c-6c7776caf8f9',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_fields': {'name': 'Claude Fable 5.2 (Low, Default Fallback)',
                                                        'slug': 'claude-fable-5-2-low',
                                                        'release_date': '2026-11-09',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'source_model_id': 'cfc7acb1-d903-4858-9b6c-6c7776caf8f9',
                                      'basis': 'Manual comparison of exact AA identities; shared version '
                                               'label, distinct configuration labels. No inference of '
                                               'provider routing, supported API settings or identical '
                                               'underlying weights. Exact ID, creator object, original '
                                               'name/slug and release date match the independently retained '
                                               'new snapshot. Existing product-label grouping was '
                                               're-reviewed; no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.2',
                                                                     'release_date': '2026-11-09'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:cfc7acb1-d903-4858-9b6c-6c7776caf8f9',
              'release_version': {'product_version': '5.2', 'release_date': '2026-11-09'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'd366dfa1-d940-4788-aa73-d298c45699b3',
              'family_id': 'google:gemini-4-argon:r2026-09-30',
              'expected_identity': {'name': 'Gemini 4 Argon (High)',
                                    'slug': 'gemini-4-argon',
                                    'release_date': '2026-09-30',
                                    'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                    'creator_name': 'Google'},
              'configuration': {'reasoning_label': 'High',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:d366dfa1-d940-4788-aa73-d298c45699b3',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'd366dfa1-d940-4788-aa73-d298c45699b3',
                                      'source_fields': {'name': 'Gemini 4 Argon (High)',
                                                        'slug': 'gemini-4-argon',
                                                        'release_date': '2026-09-30',
                                                        'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
                                                        'creator_name': 'Google'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. Single reviewed product entry; '
                                               'this asserts its exact labeled identity, not relationships '
                                               'to unreviewed variants. Different product versions, '
                                               'releases, sizes, Preview, quantization and routes are not '
                                               'automatically included. This is curated product grouping, '
                                               'not verified identical weights, deployment or provider '
                                               'equivalence. Exact ID, creator object, original name/slug '
                                               'and release date match the independently retained new '
                                               'snapshot. Existing product-label grouping was re-reviewed; '
                                               'no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '4 Argon',
                                                                     'release_date': '2026-09-30'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'faddc6d9-2c14-445f-9b28-56726f59c793',
              'configuration_key': 'aa-configuration:d366dfa1-d940-4788-aa73-d298c45699b3',
              'release_version': {'product_version': '4 Argon', 'release_date': '2026-09-30'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'df5bf99d-d228-4715-b41b-19ca86118777',
              'family_id': 'anthropic:claude-opus-5.5:default-fallback:r2026-09-22',
              'expected_identity': {'name': 'Claude Opus 5.5 (Xhigh, Default Fallback)',
                                    'slug': 'claude-opus-5-5-xhigh',
                                    'release_date': '2026-09-22',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'Xhigh',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:df5bf99d-d228-4715-b41b-19ca86118777',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'df5bf99d-d228-4715-b41b-19ca86118777',
                                      'source_fields': {'name': 'Claude Opus 5.5 (Xhigh, Default Fallback)',
                                                        'slug': 'claude-opus-5-5-xhigh',
                                                        'release_date': '2026-09-22',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. The enumerated entries share this AA '
                                               'product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.5',
                                                                     'release_date': '2026-09-22'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:df5bf99d-d228-4715-b41b-19ca86118777',
              'release_version': {'product_version': '5.5', 'release_date': '2026-09-22'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'e05a4828-0536-4876-870d-a235023f992b',
              'family_id': 'openai:gpt-6-astra:r2026-09-03',
              'expected_identity': {'name': 'GPT-6 Astra (High)',
                                    'slug': 'gpt-6-astra-high',
                                    'release_date': '2026-09-03',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'High',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:e05a4828-0536-4876-870d-a235023f992b',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'e05a4828-0536-4876-870d-a235023f992b',
                                      'source_fields': {'name': 'GPT-6 Astra (High)',
                                                        'slug': 'gpt-6-astra-high',
                                                        'release_date': '2026-09-03',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6 Astra',
                                                                     'release_date': '2026-09-03'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:e05a4828-0536-4876-870d-a235023f992b',
              'release_version': {'product_version': '6 Astra', 'release_date': '2026-09-03'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'e97a4ef5-e817-480e-9595-12f81dc4974f',
              'family_id': 'openai:gpt-6-astra:r2026-09-03',
              'expected_identity': {'name': 'GPT-6 Astra (Medium)',
                                    'slug': 'gpt-6-astra-medium',
                                    'release_date': '2026-09-03',
                                    'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                    'creator_name': 'OpenAI'},
              'configuration': {'reasoning_label': 'Medium',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:e97a4ef5-e817-480e-9595-12f81dc4974f',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'e97a4ef5-e817-480e-9595-12f81dc4974f',
                                      'source_fields': {'name': 'GPT-6 Astra (Medium)',
                                                        'slug': 'gpt-6-astra-medium',
                                                        'release_date': '2026-09-03',
                                                        'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
                                                        'creator_name': 'OpenAI'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. No routing identity is asserted where the AA '
                                               'label does not state one. The enumerated entries share this '
                                               'AA product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '6 Astra',
                                                                     'release_date': '2026-09-03'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e67e56e3-15cd-43db-b679-da4660a69f41',
              'configuration_key': 'aa-configuration:e97a4ef5-e817-480e-9595-12f81dc4974f',
              'release_version': {'product_version': '6 Astra', 'release_date': '2026-09-03'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2',
              'family_id': 'meta:muse-wonder-full:r2026-10-12',
              'expected_identity': {'name': 'Muse Wonder Full (Max)',
                                    'slug': 'muse-wonder-full',
                                    'release_date': '2026-10-12',
                                    'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
                                    'creator_name': 'Meta'},
              'configuration': {'reasoning_label': 'Max',
                                'routing_label': None,
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2',
                                'size_label': 'Full',
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2',
                                      'source_fields': {'name': 'Muse Wonder Full (Max)',
                                                        'slug': 'muse-wonder-full',
                                                        'release_date': '2026-10-12',
                                                        'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
                                                        'creator_name': 'Meta'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only this exact Full size label is included. '
                                               'No routing identity is asserted where the AA label does not '
                                               'state one. Single reviewed product entry; this asserts its '
                                               'exact labeled identity, not relationships to unreviewed '
                                               'variants. Different product versions, releases, sizes, '
                                               'Preview, quantization and routes are not automatically '
                                               'included. This is curated product grouping, not verified '
                                               'identical weights, deployment or provider equivalence. Exact '
                                               'ID, creator object, original name/slug and release date '
                                               'match the independently retained new snapshot. Existing '
                                               'product-label grouping was re-reviewed; no weights or '
                                               'provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': 'Wonder Full',
                                                                     'release_date': '2026-10-12'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'e1694725-0192-4e54-b1b8-c97e816c6cbe',
              'configuration_key': 'aa-configuration:e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2',
              'release_version': {'product_version': 'Wonder Full', 'release_date': '2026-10-12'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'f314eade-2232-44bf-a3ab-9b326bc67de6',
              'family_id': 'anthropic:claude-opus-5.5:default-fallback:r2026-09-22',
              'expected_identity': {'name': 'Claude Opus 5.5 (High, Default Fallback)',
                                    'slug': 'claude-opus-5-5-high',
                                    'release_date': '2026-09-22',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'High',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:f314eade-2232-44bf-a3ab-9b326bc67de6',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_model_id': 'f314eade-2232-44bf-a3ab-9b326bc67de6',
                                      'source_fields': {'name': 'Claude Opus 5.5 (High, Default Fallback)',
                                                        'slug': 'claude-opus-5-5-high',
                                                        'release_date': '2026-09-22',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'basis': 'Explicit review of the exact AA IDs, creator, complete '
                                               'product/version labels, release date and listed reasoning '
                                               'configurations. Only the explicitly labeled Default Fallback '
                                               'route is included. The enumerated entries share this AA '
                                               'product label and release; configurations stay distinct. '
                                               'Different product versions, releases, sizes, Preview, '
                                               'quantization and routes are not automatically included. This '
                                               'is curated product grouping, not verified identical weights, '
                                               'deployment or provider equivalence. Exact ID, creator '
                                               'object, original name/slug and release date match the '
                                               'independently retained new snapshot. Existing product-label '
                                               'grouping was re-reviewed; no weights or provider equivalence '
                                               'asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.5',
                                                                     'release_date': '2026-09-22'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:f314eade-2232-44bf-a3ab-9b326bc67de6',
              'release_version': {'product_version': '5.5', 'release_date': '2026-09-22'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'},
             {'model_id': 'fdc1913b-9497-45ef-83f7-17dae756f37e',
              'family_id': 'anthropic:claude-fable-5.2',
              'expected_identity': {'name': 'Claude Fable 5.2 (High, Default Fallback)',
                                    'slug': 'claude-fable-5-2-high',
                                    'release_date': '2026-11-09',
                                    'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                    'creator_name': 'Anthropic'},
              'configuration': {'reasoning_label': 'High',
                                'routing_label': 'Default Fallback',
                                'verification_status': 'aa_label_only',
                                'configuration_key': 'aa-configuration:fdc1913b-9497-45ef-83f7-17dae756f37e',
                                'size_label': None,
                                'preview_label': None,
                                'quantization_label': None,
                                'unspecified_labels_status': 'unknown_not_inferred'},
              'supporting_evidence': {'snapshot_id': 'd83dcce1043c1044',
                                      'data_mode': 'live',
                                      'retrieved_at': '2026-11-18T02:17:14.526737+00:00',
                                      'source_url': 'https://artificialanalysis.ai/api/v2/language/models/free',
                                      'source_fields': {'name': 'Claude Fable 5.2 (High, Default Fallback)',
                                                        'slug': 'claude-fable-5-2-high',
                                                        'release_date': '2026-11-09',
                                                        'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
                                                        'creator_name': 'Anthropic'},
                                      'source_model_id': 'fdc1913b-9497-45ef-83f7-17dae756f37e',
                                      'basis': 'Manual comparison of exact AA identities; shared version '
                                               'label, distinct configuration labels. No inference of '
                                               'provider routing, supported API settings or identical '
                                               'underlying weights. Exact ID, creator object, original '
                                               'name/slug and release date match the independently retained '
                                               'new snapshot. Existing product-label grouping was '
                                               're-reviewed; no weights or provider equivalence asserted.',
                                      'review': {'review_date': '2026-11-17',
                                                 'status': 'reviewed_aa_product_label_only',
                                                 'mapping_version': 'aa-label-families-v3',
                                                 'release_version': {'product_version': '5.2',
                                                                     'release_date': '2026-11-09'},
                                                 'scope': 'Repository product-label curation from retained '
                                                          'AA identity evidence; no official equivalence '
                                                          'verification.'},
                                      'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
                                      'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                                                       'historical_snapshot_id': 'eec442cab98cf613',
                                                       'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                                                       'review_date': '2026-11-17',
                                                       'reviewed_entries': 23,
                                                       'scope': 'Exact retained AA identity revalidation '
                                                                'only; existing product/version, release, '
                                                                'size and routing boundaries remain '
                                                                'unchanged. No metric evidence or provider '
                                                                'equivalence transferred.'}},
              'snapshot_id': 'd83dcce1043c1044',
              'creator_id': 'f0aa413f-e8ae-4fcd-9c48-0e049f4f3128',
              'configuration_key': 'aa-configuration:fdc1913b-9497-45ef-83f7-17dae756f37e',
              'release_version': {'product_version': '5.2', 'release_date': '2026-11-09'},
              'review_status': 'reviewed_aa_product_label_only',
              'mapping_version': 'aa-label-families-v3'}],
 'snapshot_id': 'd83dcce1043c1044',
 'snapshot_fingerprint': 'd83dcce1043c1044f21b298a975d9951175a44d9bce759221a2ab454ab790e47',
 'revalidation': {'historical_mapping_version': 'aa-label-families-v2',
                  'historical_snapshot_id': 'eec442cab98cf613',
                  'historical_snapshot_fingerprint': 'eec442cab98cf6132fc0c55cb17ecef74b853759319f751d23b4e0fabc58866c',
                  'review_date': '2026-11-17',
                  'reviewed_entries': 23,
                  'scope': 'Exact retained AA identity revalidation only; existing product/version, release, '
                           'size and routing boundaries remain unchanged. No metric evidence or provider '
                           'equivalence transferred.'}}
