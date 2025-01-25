#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

   Copyright 2014-2024 OpenEEmeter contributors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

"""
from datetime import datetime

from eemeter.eemeter import HourlyBaselineData, HourlyReportingData, HourlyModel, HourlySolarSettings, HourlyNonSolarSettings
from eemeter.eemeter.common.exceptions import DataSufficiencyError
from eemeter.eemeter.common.warnings import EEMeterWarning
from eemeter.common.test_data import load_test_data
import numpy as np
import pandas as pd
import pytest
from math import ceil

_TEST_METER = 110596


@pytest.fixture
def hourly_data():
    baseline, reporting = load_test_data("hourly_treatment_data")
    return baseline.loc[_TEST_METER], reporting.loc[_TEST_METER]

@pytest.fixture
def baseline(hourly_data):
    baseline, _ = hourly_data
    baseline.loc[baseline["observed"] > 513, "observed"] = 0  #quick extreme value removal
    baseline["ghi"] = (np.sin(np.linspace(0, 2*np.pi*len(baseline), len(baseline))) * 40).round(2) + 40
    return baseline
    
@pytest.fixture
def reporting(hourly_data):
    _, reporting = hourly_data
    reporting["ghi"] = (np.sin(np.linspace(0, 2*np.pi*len(reporting), len(reporting))) * 40).round(2) + 40
    return reporting

@pytest.fixture
def baseline_ghi(baseline):
    #generate ghi as a sin wave daily period peaking afternoon
    baseline["ghi"] = np.sin(np.linspace(0, 2*np.pi, len(baseline)))
    return baseline

def test_good_data(baseline, reporting):
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    reporting_data = HourlyReportingData(reporting, is_electricity_data=True)
    hm = HourlyModel().fit(baseline_data)
    p1 = hm.predict(reporting_data)
    serialized = hm.to_json()
    hm2 = HourlyModel.from_json(serialized)
    p2 = hm2.predict(reporting_data)
    assert p1.equals(p2)

def test_misaligned_data(baseline, reporting):
    reporting.index = reporting.index.shift(8, freq="H")
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    reporting_data = HourlyReportingData(reporting, is_electricity_data=True)
    hm = HourlyModel().fit(baseline_data)
    hm.predict(reporting_data)

def test_tz_naive(baseline):
    baseline.index = baseline.index.tz_localize(None)
    with pytest.raises(ValueError):
        HourlyBaselineData(baseline, is_electricity_data=True)

def test_tz_mismatch(baseline):
    # might allow automatic adjustment from the model in the future, but hard requirement for now
    baseline.index = baseline.index.tz_convert("US/Pacific")
    reporting = baseline.copy()
    reporting.index = reporting.index.tz_convert("US/Eastern")
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    reporting_data = HourlyReportingData(reporting, is_electricity_data=True)
    hm = HourlyModel().fit(baseline_data)
    with pytest.raises(ValueError):
        hm.predict(reporting_data)

def test_predict_missing_fit_features(baseline, reporting):
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    hm = HourlyModel(settings=HourlySolarSettings()).fit(baseline_data)
    reporting.drop("ghi", axis=1, inplace=True)
    reporting_data = HourlyReportingData(reporting, is_electricity_data=True)
    with pytest.raises(ValueError):
        hm.predict(reporting_data)

def test_nonsolar_predict_with_ghi(baseline, reporting, caplog):
    baseline.drop("ghi", axis=1, inplace=True)
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    hm = HourlyModel().fit(baseline_data)
    reporting_data = HourlyReportingData(reporting, is_electricity_data=True)
    with caplog.at_level("WARNING"):
        hm.predict(reporting_data)
        assert "GHI" in caplog.text

def test_forced_solar_model_fit_no_ghi(baseline):
    baseline = baseline.drop("ghi", axis=1)
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    with pytest.raises(ValueError):
        HourlyModel(settings=HourlySolarSettings()).fit(baseline_data)

def test_forced_nonsolar_model_fit_with_ghi(baseline):
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    hm = HourlyModel(settings=HourlyNonSolarSettings()).fit(baseline_data)
    assert [w for w in hm.warnings if w.qualified_name == "eemeter.potential_model_mismatch"]

def test_no_data(baseline):
    baseline["observed"] = 0
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(baseline_data)

def test_negative_meter_values(baseline):
    baseline.loc["2018-01-08", "observed"] = -1

    # gas data can't be negative
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=False)
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(baseline_data)

    # elec can
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    HourlyModel().fit(baseline_data)

def test_invalid_baseline_lengths(baseline):
    #TODO import min/max length from constants
    MAX_BASELINE_HOURS = 8760
    MIN_BASELINE_HOURS = ceil(MAX_BASELINE_HOURS * 0.9) - 24
    short_df = baseline.iloc[:MIN_BASELINE_HOURS]

    extra_day = baseline.iloc[-24:]
    extra_day.index += pd.Timedelta(days=1)
    long_df = pd.concat([baseline, extra_day])

    short_baseline = HourlyBaselineData(short_df, is_electricity_data=True)
    long_baseline = HourlyBaselineData(long_df, is_electricity_data=True)
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(short_baseline)
    hm_short = HourlyModel().fit(short_baseline, ignore_disqualification=True)
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(long_baseline)
    hm_long = HourlyModel().fit(long_baseline, ignore_disqualification=True)

def test_low_freq_temp(baseline):
    baseline["temperature"] = baseline["temperature"].resample('D').mean()
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    assert_dq(baseline_data, ["eemeter.sufficiency_criteria.too_many_days_with_missing_temperature_data"])
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(baseline_data)

def test_low_freq_meter(baseline):
    baseline["observed"] = baseline["observed"].resample('D').mean()
    baseline_data = HourlyBaselineData(baseline, is_electricity_data=True)
    assert_dq(baseline_data, ["eemeter.sufficiency_criteria.too_many_days_with_missing_meter_data"])
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(baseline_data)

def test_monthly_percentage(baseline):
    missing_idx = pd.date_range(start=baseline.index.min(), end=baseline.index.max(), freq="H")
    #create datetimeindex where a little over 10% of days are missing each month
    missing_idx = missing_idx[missing_idx.day < 4]
    invalid_baseline = baseline[~baseline.index.isin(missing_idx)]
    #create datetimeindex where a little under 10% of days are missing each month
    missing_idx = missing_idx[missing_idx.day < 3]
    valid_baseline = baseline[~baseline.index.isin(missing_idx)]

    baseline_data = HourlyBaselineData(invalid_baseline, is_electricity_data=True)
    assert_dq(baseline_data, ["eemeter.sufficiency_criteria.missing_monthly_temperature_data"])
    with pytest.raises(DataSufficiencyError):
        HourlyModel().fit(baseline_data)
    baseline_data = HourlyBaselineData(valid_baseline, is_electricity_data=True)
    HourlyModel().fit(baseline_data)

def test_hourly_consecutive_missing(baseline):
    pass

def assert_dq(data, expected_disqualifications):
    remaining_dq = set(expected_disqualifications)
    for dq in data.disqualification:
        if dq.qualified_name in remaining_dq:
            remaining_dq.remove(dq.qualified_name)
    assert not remaining_dq
    
    

"""TEST CASES
TODO get a couple example meters with GHI, potentially some supplemental features?
    * at least one solar and one non-solar

* good, clean data with known fit/predict numbers to check for regressions
* good meter, bad temperature
    * daily frequency temp
    * too many missing values
    * tz-naive
* good temp, bad meter
    * daily/worse frequency meter
    * too many missing values
    * tz-naive
* no GHI, attempting solar
* GHI, attempting nonsolar (warning?)
* test against supplemental data logic -> should require a flag in model to fit
* all 0s in meter data -> leads to full nan
* test valid interpolations
* test with various days removed due to interpolation during fit()
    * include day where timezone shifts in either direction
* test edge case, nearly valid, but not allowed interpolations (7 consecutive hours, etc)
    * should still happen to allow model fit, but add (and test for) DQ
* test a few DQs - baseline length, etc
* unmarked net metering flag - includes warning
* all above tests using from_series in parallel, verifying that output is identical
* test with various pv_start values
"""