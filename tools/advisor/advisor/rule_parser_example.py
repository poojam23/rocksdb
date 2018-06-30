# Copyright (c) 2011-present, Facebook, Inc.  All rights reserved.
#  This source code is licensed under both the GPLv2 (found in the
#  COPYING file in the root directory) and Apache 2.0 License
#  (found in the LICENSE.Apache file in the root directory).

import argparse
from advisor.db_log_parser import DatabaseLogs
from advisor.db_options_parser import DatabaseOptions
from advisor.db_stats_fetcher import OdsStatsFetcher
import pickle
from advisor.rule_parser import RulesSpec


def main(args):
    # Load the rules with their conditions and suggestions.
    db_rules = RulesSpec(args.rules_spec)
    db_rules.load_rules_from_spec()
    # Perform some basic sanity checks for each section.
    db_rules.perform_section_checks()

    conditions_dict = db_rules.get_conditions_dict()
    suggestions_dict = db_rules.get_suggestions_dict()

    # Initialise the data sources.
    data_sources = []
    data_sources.append(DatabaseOptions(args.rocksdb_options))
    data_sources.append(
        DatabaseLogs(
            args.rocksdb_log_prefix, data_sources[0].get_column_families()
        )
    )
    if args.ods_client:
        data_sources.append(
            OdsStatsFetcher(
                args.ods_client,
                args.ods_entities,
                args.ods_key_prefix)
        )

    # Check for the conditions read in from the Rules spec, if triggered.
    column_families = data_sources[0].get_column_families()
    triggered_rules = db_rules.get_triggered_rules(
        data_sources, column_families
    )

    with open(args.output_file, 'wb') as fp:
        pickle.dump(conditions_dict, fp, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(suggestions_dict, fp, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(triggered_rules, fp, protocol=pickle.HIGHEST_PROTOCOL)

    db_rules.print_rules(triggered_rules)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='This script is used for\
        gauging rocksdb performance using as input: Rocksdb LOG, OPTIONS,\
        performance context, command-line statistics and statistics published\
        on ODS and providing as output: suggestions to improve Rocksdb\
        performance')
    parser.add_argument('--rules_spec', required=True, type=str)
    parser.add_argument('--rocksdb_options', required=True, type=str)
    parser.add_argument('--rocksdb_log_prefix', required=True, type=str)
    parser.add_argument('--output_file', required=True, type=str)
    # parser.add_argument("-v", "--verbose", action="store_true")
    '''
    ods_entities and ods_key_prefix are required for ODS based conditions.
    By default, the data fetched from ODS is for the last 3 hours. If
    ods_end_time is not specified, it is assumed to be the current time.
    '''
    parser.add_argument('--ods_client', type=str)
    parser.add_argument('--ods_entities', type=str)
    parser.add_argument('--ods_key_prefix', type=str)
    args = parser.parse_args()
    main(args)
