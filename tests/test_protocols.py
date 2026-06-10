from zer0factor.core import Zer0ShareDataProvider
from zer0factor.core.protocols import DataProvider, IndustrySource, UniverseSource


class _FakePro:
    def universe(self, *, universe=None, start_date=None, end_date=None, fields=None):
        raise NotImplementedError

    def index_member_all(self, fields=None):
        raise NotImplementedError


def test_zer0share_provider_satisfies_data_provider():
    assert isinstance(Zer0ShareDataProvider(pro=None), DataProvider)


def test_fake_pro_satisfies_source_protocols():
    assert isinstance(_FakePro(), UniverseSource)
    assert isinstance(_FakePro(), IndustrySource)
