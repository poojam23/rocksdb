# Copyright (c) 2011-present, Facebook, Inc.  All rights reserved.
#  This source code is licensed under both the GPLv2 (found in the
#  COPYING file in the root directory) and Apache 2.0 License
#  (found in the LICENSE.Apache file in the root directory).

from abc import abstractmethod
from advisor.db_log_parser import DataSource
from enum import Enum
import math


NO_ENTITY = 'ENTITY_PLACEHOLDER'


class TimeSeriesData(DataSource):
    class Behavior(Enum):
        bursty = 1
        evaluate_expression = 2

    class AggregationOperator(Enum):
        avg = 1
        max = 2
        min = 3
        latest = 4
        oldest = 5

    def __init__(self):
        super().__init__(DataSource.Type.TIME_SERIES)
        self.keys_ts = None  # Dict[entity, Dict[key, Dict[timestamp, value]]]

    @abstractmethod
    def get_keys_from_conditions(self):
        pass

    @abstractmethod
    def fetch_timeseries(self):
        pass

    def fetch_burst_epochs(
        self, statistic, window_sec, threshold, percent=False
    ):
        # type: (str, int, float, bool) -> Dict[int, float]
        if window_sec < self.stats_freq_sec:
            window_sec = self.stats_freq_sec
        window_samples = math.ceil(window_sec / self.stats_freq_sec)
        burst_epochs = {}
        for entity in self.keys_ts:
            if statistic not in self.keys_ts[entity]:
                continue
            timestamps = sorted(list(self.keys_ts[entity][statistic].keys()))
            for ix in range(window_samples, len(timestamps), 1):
                first_ts = timestamps[ix - window_samples]
                last_ts = timestamps[ix]
                first_val = self.keys_ts[entity][statistic][first_ts]
                last_val = self.keys_ts[entity][statistic][last_ts]
                diff = last_val - first_val
                if percent:
                    diff = diff * 100 / first_val
                rate = (diff * self.duration_sec) / (last_ts - first_ts)
                if rate >= threshold:
                    if entity not in burst_epochs:
                        burst_epochs[entity] = {}
                    burst_epochs[entity][last_ts] = rate
        return burst_epochs

    def fetch_aggregated_values(self, statistics, aggregation_op):
        # type: (str, AggregationOperator) -> Dict[str, Dict[str, float]]
        # returned object is Dict[entity, Dict[key, aggregated_value]]
        result = {}
        for et in self.keys_ts:
            for stat in statistics:
                if stat not in self.keys_ts[et]:
                    continue
                agg_val = None
                if aggregation_op is self.AggregationOperator.latest:
                    latest_timestamp = max(list(self.keys_ts[et][stat].keys()))
                    agg_val = self.keys_ts[et][stat][latest_timestamp]
                elif aggregation_op is self.AggregationOperator.oldest:
                    oldest_timestamp = min(list(self.keys_ts[et][stat].keys()))
                    agg_val = self.keys_ts[et][stat][oldest_timestamp]
                elif aggregation_op is self.AggregationOperator.max:
                    agg_val = max(list(self.keys_ts[et][stat].values()))
                elif aggregation_op is self.AggregationOperator.min:
                    agg_val = min(list(self.keys_ts[et][stat].values()))
                elif aggregation_op is self.AggregationOperator.avg:
                    values = list(self.keys_ts[et][stat].values())
                    agg_val = sum(values) / len(values)
                if et not in result:
                    result[et] = {}
                result[et][stat] = agg_val
        return result

    def check_and_trigger_conditions(self, conditions):
        # get the list of statistics that need to be fetched
        reqd_keys = self.get_keys_from_conditions(conditions)
        # fetch the required statistics and populate the map 'keys_ts'
        self.fetch_timeseries(reqd_keys)
        # Trigger the appropriate conditions
        for cond in conditions:
            complete_keys = self.get_keys_from_conditions([cond])
            if cond.behavior is self.Behavior.bursty:
                statistic = complete_keys[0]  # there should be only one key
                result = self.fetch_burst_epochs(
                        statistic, cond.window_sec, cond.rate_threshold, True
                )
                if result:
                    cond.set_trigger(result)
            elif cond.behavior is self.Behavior.evaluate_expression:
                result = self.fetch_aggregated_values(
                        complete_keys, cond.aggregation_op
                )
                entity_evaluation_dict = {}
                for entity in result:
                    keys = [
                        result[entity][key]
                        for key in complete_keys
                        if key in result[entity]
                    ]  # keys should be in the same order as complete_keys
                    if len(keys) != len(complete_keys):
                        continue
                    try:
                        if eval(cond.expression):
                            entity_evaluation_dict[entity] = keys
                    except Exception as e:
                        print('TimeSeriesData check_and_trigger: ' + str(e))
                if entity_evaluation_dict:
                    cond.set_trigger(entity_evaluation_dict)
