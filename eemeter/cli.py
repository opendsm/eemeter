from collections import OrderedDict
import datetime
import pytz
import csv
import os
import click
import pandas as pd
from scipy import stats
import numpy as np
from eemeter.structures import EnergyTrace
from eemeter.io.serializers import ArbitraryStartSerializer
from eemeter.ee.meter import EnergyEfficiencyMeter
from eemeter.processors.dispatchers import (
    get_approximate_frequency,
)
from eemeter.modeling.models.caltrack_daily import CaltrackDailyModel
from eemeter.modeling.models.caltrack import CaltrackMonthlyModel


@click.group()
def cli():
    pass


def serialize_meter_input(
        trace, zipcode, retrofit_start_date, retrofit_end_date):
    data = OrderedDict([
        ("type", "SINGLE_TRACE_SIMPLE_PROJECT"),
        ("trace", trace_serializer(trace)),
        ("project", project_serializer(
            zipcode, retrofit_start_date, retrofit_end_date
        )),
    ])
    return data


def trace_serializer(trace):
    data = OrderedDict([
        ("type", "ARBITRARY_START"),
        ("interpretation", trace.interpretation),
        ("unit", trace.unit),
        ("trace_id", trace.trace_id),
        ("interval", trace.interval),
        ("records", [
            OrderedDict([
                ("start", start.isoformat()),
                ("value", record.value if pd.notnull(record.value) else None),
                ("estimated", bool(record.estimated)),
            ])
            for start, record in trace.data.iterrows()
        ]),
    ])
    return data


def project_serializer(zipcode, retrofit_start_date, retrofit_end_date):
    data = OrderedDict([
        ("type", "PROJECT_WITH_SINGLE_MODELING_PERIOD_GROUP"),
        ("zipcode", zipcode),
        ("project_id", 'PROJECT_ID_ABC'),
        ("modeling_period_group", OrderedDict([
            ("baseline_period", OrderedDict([
                ("start", None),
                ("end", retrofit_start_date.isoformat()),
            ])),
            ("reporting_period", OrderedDict([
                ("start", retrofit_end_date.isoformat()),
                ("end", None),
            ]))
        ]))
    ])
    return data


def read_csv(path):
    result = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            result.append(row)
    return result


def date_reader(date_format):
    def reader(raw):
        if raw.strip() == '':
            return None
        return datetime.datetime.strptime(raw, date_format)\
                                .replace(tzinfo=pytz.UTC)
    return reader


date_readers = [
    date_reader('%Y-%m-%d'),
    date_reader('%m/%d/%Y'),
    date_reader('%Y-%m-%d %H:%M:%S'),
    date_reader('%Y-%m-%dT%H:%M:%S'),
    date_reader('%Y-%m-%dT%H:%M:%SZ'),
]


def flexible_date_reader(raw):
    for reader in date_readers:
        try:
            return reader(raw)
        except:
            pass
    raise ValueError("Unable to parse date")


def build_trace(trace_records):
    if trace_records[0]['interpretation'] == 'gas':
        unit = "THM"
        interpretation = "NATURAL_GAS_CONSUMPTION_SUPPLIED"
    else:
        unit = "KWH"
        interpretation = "ELECTRICITY_CONSUMPTION_SUPPLIED"
    trace_object = EnergyTrace(
        records=trace_records,
        unit=unit,
        interpretation=interpretation,
        serializer=ArbitraryStartSerializer(),
        trace_id=trace_records[0]['project_id']
    )
    return trace_object


def build_traces(trace_records):
    current_trace_id = None
    current_trace = []
    trace_objects = []

    # Split the concatenated traces into individual traces
    for record in trace_records:
        trace_id = record["project_id"] + " " + record["interpretation"]
        if current_trace_id is None:
            current_trace_id = trace_id
            current_trace.append(record)
        elif current_trace_id == trace_id:
            current_trace.append(record)
        else:
            trace_objects.append(build_trace(current_trace))
            current_trace = [record]
            current_trace_id = trace_id
    trace_objects.append(build_trace(current_trace))

    return trace_objects


def run_meter(project, trace_object, options=None):
    print("\n\nRunning a meter for %s %s" % (
        trace_object.trace_id, trace_object.interpretation)
    )
    meter_input = serialize_meter_input(
        trace_object,
        project['zipcode'],
        project['project_start'],
        project['project_end']
    )

    ee = EnergyEfficiencyMeter()

    if options is not None and \
       'ignore_data_sufficiency' in options.keys() and \
       options['ignore_data_sufficiency'] == True:
        trace_frequency = get_approximate_frequency(trace_object)
        if trace_frequency not in ['H', 'D', '15T', '30T']:
             trace_frequency = None
        selector = (trace_object.interpretation, trace_frequency)
        model = ee._get_model(None, selector)
    
        model_class, model_kwargs = model
    
        if model_class == CaltrackMonthlyModel:
            model_kwargs['min_contiguous_baseline_months'] = 0
            model_kwargs['min_contiguous_reporting_months'] = 0
        else:
            model_kwargs['min_contiguous_months'] = 0

    meter_output = ee.evaluate(meter_input)

    # Compute and output the annualized weather normal
    series_name = \
        'Cumulative baseline model minus reporting model, normal year'
    awn = [i['value'][0] for i in meter_output['derivatives']
           if i['series'] == series_name]
    if len(awn) > 0:
        awn = awn[0]
    else:
        awn = None
    awn_var = [i['variance'][0] for i in meter_output['derivatives']
               if i['series'] == series_name]
    if len(awn_var) > 0:
        awn_var = awn_var[0]
    else:
        awn_var = None
    awn_confint = []
    if awn is not None and awn_var is not None:
        awn_confint = stats.norm.interval(0.68, loc=awn, scale=np.sqrt(awn_var))

    if len(awn_confint) > 1:
        print("Normal year savings estimate:")
        print("  {:f}\n  68% confidence interval: ({:f}, {:f})".
              format(awn, awn_confint[0], awn_confint[1]))
    else:
        print("Normal year savings estimates not computed due to error:")
        bl_traceback = meter_output['modeled_energy_trace']['fits']['baseline']['traceback']
        rp_traceback = meter_output['modeled_energy_trace']['fits']['reporting']['traceback']
        if bl_traceback is not None:
            print(bl_traceback)
        if rp_traceback is not None:
            print(rp_traceback)

    # Compute and output the weather normalized reporting period savings
    series_name = \
        'Cumulative baseline model minus observed, reporting period'
    rep = [i['value'][0] for i in meter_output['derivatives']
           if i['series'] == series_name]
    if len(rep) > 0:
        rep = rep[0]
    else:
        rep = None
    rep_var = [i['variance'][0] for i in meter_output['derivatives']
               if i['series'] == series_name]
    if len(rep_var) > 0:
        rep_var = rep_var[0]
    else:
        rep_var = None
    rep_confint = []
    if rep is not None and rep_var is not None:
        rep_confint = stats.norm.interval(0.68, loc=rep, scale=np.sqrt(rep_var))
    else:
        rep_confint = []

    if len(rep_confint) > 1:
        print("Reporting period savings estimate:")
        print("  {:f}\n  68% confidence interval: ({:f}, {:f})".
              format(rep, rep_confint[0], rep_confint[1]))
    else:
        print("Reporting period savings estimates not computed due to error:")
        print(meter_output['modeled_energy_trace']['fits']['baseline']['traceback'])

    return meter_output


def _analyze(inputs_path, options=None):
    projects, trace_objects = _load_projects_and_traces(inputs_path)

    meter_output_list = list()
    for project in projects:
        for trace_object in trace_objects:
            if trace_object.trace_id == project['project_id']:
                meter_output_list.append(run_meter(project, trace_object, options=options))

    return meter_output_list


def _load_projects_and_traces(inputs_path):
    projects = read_csv(os.path.join(inputs_path, 'projects.csv'))
    traces = read_csv(os.path.join(inputs_path, 'traces.csv'))

    for row in traces:
        row['start'] = flexible_date_reader(row['start'])

    for row in projects:
        row['project_start'] = flexible_date_reader(row['project_start'])
        row['project_end'] = flexible_date_reader(row['project_end'])

    trace_objects = build_traces(traces)
    return projects, trace_objects


def _get_sample_inputs_path():
    path = os.path.realpath(__file__)
    cwd = os.path.dirname(path)
    sample_inputs_path = os.path.join(cwd, 'sample_data')
    return sample_inputs_path


@cli.command()
def sample():
    sample_inputs_path = _get_sample_inputs_path()
    print("Going to analyze the sample data set")
    print("")
    _analyze(sample_inputs_path)


@cli.command()
@click.argument('inputs_path', type=click.Path(exists=True))
@click.option('--ignore-data-sufficiency', is_flag=True,
              help='Ignore the data sufficiency requirements.')
def analyze(inputs_path, ignore_data_sufficiency):
    options = { 'ignore_data_sufficiency': ignore_data_sufficiency } 
    _analyze(inputs_path, options=options)
