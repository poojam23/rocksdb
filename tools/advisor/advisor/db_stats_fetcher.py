from advisor.db_timeseries_parser import TimeSeriesData
import subprocess


class OdsTimeSeriesData(TimeSeriesData):
    # class constants
    OUTPUT_FILE = 'temp/stats_out.tmp'
    ERROR_FILE = 'temp/stats_err.tmp'
    COMMAND = (
        "%s --entity=%s --key=%s --tstart=%s --tend=%s" +
        " --transform=%s --showtime"
    )
    RATE_TRANSFORM_DESC = "rate(%,15m,duration=60)"

    # static methods
    @staticmethod
    def _get_string_in_quotes(value):
        return '"' + str(value) + '"'

    @staticmethod
    def _get_time_value_pair(pair_string):
        pair_string = pair_string.replace('[', '')
        pair_string = pair_string.replace(']', '')
        pair = pair_string.split(',')
        first = int(pair[0].strip())
        second = float(pair[1].strip())
        return [first, second]

    def __init__(self, client, entities, start_time, end_time, key_prefix):
        super().__init__(start_time, end_time)
        self.client = client
        self.entities = entities
        self.key_prefix = key_prefix

    def attach_prefix_to_keys(self, keys):
        client_keys = None
        if isinstance(keys, str):
            if keys.startswith('[]'):
                client_keys = self.key_prefix + keys[2:]
            else:
                client_keys = keys
        else:
            client_keys = []
            for key in keys:
                if key.startswith('[]'):
                    new_key = self.key_prefix + key[2:]
                    client_keys.append(new_key)
                else:
                    client_keys.append(key)
        return client_keys

    def execute_script(self, command):
        print('executing...')
        print(command)
        out_file = open(self.OUTPUT_FILE, "w+")
        err_file = open(self.ERROR_FILE, "w+")
        subprocess.call(command, shell=True, stdout=out_file, stderr=err_file)
        out_file.close()
        err_file.close()

    def fetch_rate_url(self, entities, keys, display_type):
        transform_desc = self.RATE_TRANSFORM_DESC
        keys = self.attach_prefix_to_keys(keys)
        if not isinstance(keys, str):
            keys = ','.join(keys)
        entities = ','.join(entities)

        command = self.COMMAND + " --url=%s"
        command = command % (
            self.client,
            self._get_string_in_quotes(entities),
            self._get_string_in_quotes(keys),
            self._get_string_in_quotes(self.start_time),
            self._get_string_in_quotes(self.end_time),
            self._get_string_in_quotes(transform_desc),
            self._get_string_in_quotes(display_type)
        )
        self.execute_script(command)
        url = ""
        with open(self.OUTPUT_FILE, 'r') as fp:
            url = fp.readline()
        return url

    def fetch_burst_epochs(self, key, threshold_lower):
        transform_desc = (
            self.RATE_TRANSFORM_DESC + ',filter(' + str(threshold_lower) + ',)'
        )
        command = self.COMMAND % (
            self.client,
            self._get_string_in_quotes(self.entities),
            self._get_string_in_quotes(key),
            self._get_string_in_quotes(self.start_time),
            self._get_string_in_quotes(self.end_time),
            self._get_string_in_quotes(transform_desc)
        )
        self.execute_script(command)
        # Parsing ODS output
        values_dict = {}
        with open(self.OUTPUT_FILE, 'r') as fp:
            for line in fp:
                token_list = line.strip().split('\t')
                entity = token_list[0]
                # key = token_list[1]
                if entity not in values_dict:
                    values_dict[entity] = {}
                list_of_lists = [
                    self._get_time_value_pair(pair_string)
                    for pair_string in token_list[2].split('],')
                ]
                value = {pair[0]: pair[1] for pair in list_of_lists}
                values_dict[entity] = value
        return values_dict

    def fetch_aggregated_values(self, keys, aggregation_operator):
        transform_desc = aggregation_operator.name
        command = self.COMMAND % (
            self.client,
            self._get_string_in_quotes(self.entities),
            self._get_string_in_quotes(','.join(keys)),
            self._get_string_in_quotes(self.start_time),
            self._get_string_in_quotes(self.end_time),
            self._get_string_in_quotes(transform_desc)
        )
        self.execute_script(command)
        # Parsing ODS output
        values_dict = {}
        with open(self.OUTPUT_FILE, 'r') as fp:
            for line in fp:
                token_list = line.strip().split('\t')
                entity = token_list[0]
                key = token_list[1]
                if entity not in values_dict:
                    values_dict[entity] = {}
                pair = self._get_time_value_pair(token_list[2])
                value = pair[1]
                values_dict[entity][key] = value
        return values_dict

    def check_and_trigger_conditions(self, conditions):
        for cond in conditions:
            complete_keys = cond.keys
            if self.key_prefix:
                complete_keys = self.attach_prefix_to_keys(cond.keys)
            if cond.behavior is self.Behavior.bursty:
                result = (
                    self.fetch_burst_epochs(complete_keys, cond.rate_threshold)
                )
                if result:
                    print(result)
                    cond.set_trigger(result)
            elif cond.behavior is self.Behavior.evaluate_expression:
                result = (
                    self.fetch_aggregated_values(
                        complete_keys, cond.aggregation_op
                    )
                )
                entity_evaluation_dict = {}
                for entity in result:
                    keys = [result[entity][key] for key in complete_keys]
                    try:
                        if eval(cond.expression):
                            entity_evaluation_dict[entity] = keys
                    except Exception as e:
                        print('OdsTimeSeriesData check_and_trigger: ' + str(e))
                if entity_evaluation_dict:
                    cond.set_trigger(entity_evaluation_dict)
