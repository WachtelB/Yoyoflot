"""Известные карты документа: Sirena плюс однозначно связанные профили."""
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def calculate(data):
    values = {document: len(data.cards.get(document, set())) for document in data.passengers}
    return [Metric('loyalty_cards', 'Карты лояльности пассажиров', 'Число известных карт', values,
                   'Карта = программа + номер. Связь по документу и карте, без ФИО. 0 означает, что известных карт не найдено.',
                   details=data.card_evidence)]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW, include_cards=True)

