from eemeter.weather import GSODWeatherSource
from eemeter.weather import TMY3WeatherSource

class Project(object):
    """
    Parameters
    ----------
    location : eemeter.location.Location
        Location object representing the location of the building in the
        project. Used for matching with weather sources unless a specific
        weather_source is provided.
    consumption : list of eemeter.consumption.ConsumptionData objects
        All available consumption data for this project.
    baseline_period : eemeter.evaluation.Period
        Date/time period for baselining.
    reporting_period : eemeter.evaluation.Period
        Date/time period for reporting.
    other_periods : list of eemeter.evaluation.Period objects
        Other named date/time periods of interest, perhaps particular seasons or years of interest.
    weather_source : eemeter.weather.WeatherSourceBase
        Source of weather data.
    weather_normal_source : eemeter.weather.WeatherSourceBase
        Source of weather normal data.
    """

    def __init__(self, location, consumption=[], baseline_period=None,
            reporting_period=None, other_periods=[], weather_source=None,
            weather_normal_source=None):
        self.location = location
        self.baseline_period = baseline_period
        self.reporting_period = reporting_period
        self.other_periods = other_periods

        if not type(consumption) == list:
            self.consumption = [consumption]
        else:
            self.consumption = consumption

        if not type(other_periods) == list:
            self.other_periods = [other_periods]
        else:
            self.other_periods = other_periods

        if weather_source is None:
            start_date, end_date = self._total_date_range()
            self.weather_source = GSODWeatherSource(location.station,
                    start_date.year, end_date.year)

        if weather_normal_source is None:
            weather_normal_source = TMY3WeatherSource(location.station)

    def _total_date_range(self):
        periods = [self.baseline_period, self.reporting_period] + \
                self.other_periods
        consumption_periods = [cd.total_period() for cd in self.consumption]
        periods += consumption_periods

        periods = [p for p in periods if p is not None]

        period_starts = [ p.start for p in periods]
        if None in period_starts:
            start_date = None
        else:
            start_date = min(period_starts)

        period_ends = [ p.start for p in periods]
        if None in period_ends:
            end_date = None
        else:
            end_date = min(period_ends)
        return start_date, end_date
