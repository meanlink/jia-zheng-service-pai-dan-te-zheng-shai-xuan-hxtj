import hashlib
import json
import math

import numpy as np
from sklearn.linear_model import Lasso, LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler

FEATURES = ('area_m2', 'dirt_level', 'obstacles', 'supplies', 'experience_years')
ALPHA = 3.0  # Minutes per standardized feature. Fixed across all fits.
MIN_HISTORY = 30
# A dirt level of 4 or 5 counts as a heavily soiled order. The comparison
# holds these out separately so a rule that only improves the average cannot
# hide a regression on the difficult jobs.
HIGH_DIRT_LEVEL = 4
MIN_HIGH_DIRT_SAMPLES = 6


class ModelUnavailable(ValueError):
    pass


def vector(row, features=FEATURES):
    return [float(row[key]) for key in features]


def split_history(history):
    """Validate and split one ordered history batch. Callers comparing rules
    must reuse the exact same batch so this split is identical for both."""
    if len(history) < MIN_HISTORY:
        raise ModelUnavailable(f'同类完单历史至少需要 {MIN_HISTORY} 条，目前 {len(history)} 条')
    # Hold out entire appointment days. The newest date in training predates validation.
    split_date = history[int(len(history) * 0.8)]['service_date']
    train = [row for row in history if row['service_date'] < split_date]
    test = [row for row in history if row['service_date'] >= split_date]
    if len(train) < 20 or len(test) < 6:
        raise ModelUnavailable('历史完单分布过于集中，无法按日期切分训练与验证集')
    return train, test, split_date


def _fit_linear(train, features):
    x_train = np.array([vector(row, features) for row in train])
    y_train = np.array([row['actual_minutes'] for row in train])
    scaler = StandardScaler().fit(x_train)
    lasso = Lasso(alpha=ALPHA, max_iter=5000, tol=1e-7).fit(scaler.transform(x_train), y_train)
    selected = np.abs(lasso.coef_) > 1e-7
    if not selected.any():
        raise ModelUnavailable('Lasso 未保留任何特征，无法出具派单解释')
    linear = LinearRegression().fit(x_train[:, selected], y_train)
    if linear.rank_ != int(selected.sum()):
        raise ModelUnavailable('入选特征的历史样本共线，无法解释回归系数')
    return x_train, y_train, scaler, lasso, linear, selected


def fingerprint(history):
    fields = [[row['id'], str(row['service_date']), vector(row), row['actual_minutes']]
              for row in history]
    return hashlib.sha256(json.dumps(fields, separators=(',', ':')).encode()).hexdigest()


def evaluate(history, features=FEATURES):
    """Measure one feature rule on a history batch without touching an order.

    Both the overall hold-out error and the heavily soiled hold-out error are
    reported so two rules can be compared on identical data and split."""
    train, test, split_date = split_history(history)
    x_train, y_train, _scaler, lasso, linear, selected = _fit_linear(train, features)
    x_test = np.array([vector(row, features) for row in test])
    predicted = linear.predict(x_test[:, selected])
    actual = np.array([row['actual_minutes'] for row in test])
    heavy = np.array([row['dirt_level'] >= HIGH_DIRT_LEVEL for row in test])
    return {
        'features': list(features),
        'selected': [key for key, kept in zip(features, selected) if kept],
        'history_count': len(history), 'train_count': len(train), 'test_count': len(test),
        'holdout_since': str(split_date), 'history_checksum': fingerprint(history),
        'holdout_mae': round(float(mean_absolute_error(actual, predicted)), 2),
        'high_dirt_mae': round(float(mean_absolute_error(actual[heavy], predicted[heavy])), 2) if heavy.any() else None,
        'high_dirt_count': int(heavy.sum()),
        'train_high_dirt_count': int(sum(row['dirt_level'] >= HIGH_DIRT_LEVEL for row in train)),
        'lasso_weights': {key: float(weight) for key, weight in zip(features, lasso.coef_)},
    }


def fit(history, order, technician, features=FEATURES):
    features = tuple(features)
    train, test, split_date = split_history(history)
    x_train, y_train, _scaler, lasso, linear, selected = _fit_linear(train, features)
    x_test = np.array([vector(row, features) for row in test])
    y_test = np.array([row['actual_minutes'] for row in test])
    row_input = {**order, 'experience_years': technician['experience_years']}
    means = x_train.mean(axis=0)
    lows, highs = x_train.min(axis=0), x_train.max(axis=0)
    weights = np.zeros(len(features))
    weights[selected] = linear.coef_
    contributions = weights * (np.array(vector(row_input, features)) - means)
    center = float(linear.intercept_ + np.dot(weights, means))
    kept = {key for key, on in zip(features, selected) if on}
    entries = []
    # Features outside the category rule are reported with a zero coefficient
    # so the per-order explanation and sensitivity scenarios stay complete.
    for key in FEATURES:
        value = float(row_input[key])
        if key in features:
            i = features.index(key)
            entries.append({
                'key': key, 'selected': key in kept, 'lasso_weight': float(lasso.coef_[i]),
                'coefficient': float(weights[i]), 'training_mean': float(means[i]), 'value': value,
                'contribution': float(contributions[i]), 'training_min': float(lows[i]),
                'training_max': float(highs[i]), 'outside_history': not lows[i] <= value <= highs[i]})
        else:
            column = np.array([float(row[key]) for row in train])
            entries.append({
                'key': key, 'selected': False, 'lasso_weight': 0.0, 'coefficient': 0.0,
                'training_mean': float(column.mean()), 'value': value, 'contribution': 0.0,
                'training_min': float(column.min()), 'training_max': float(column.max()),
                'outside_history': not column.min() <= value <= column.max()})
    return {
        'alpha': ALPHA, 'history_count': len(history), 'train_count': len(train), 'test_count': len(test),
        'history_checksum': fingerprint(history), 'holdout_since': str(split_date),
        'holdout_mae': round(float(mean_absolute_error(y_test, linear.predict(x_test[:, selected]))), 2),
        'training_mean_minutes': center, 'certificate': technician['certificate'],
        'feature_set': list(features), 'features': entries,
    }


def estimate(analysis):
    raw = analysis['training_mean_minutes'] + sum(feature['contribution'] for feature in analysis['features'])
    rounded = math.floor(raw + 0.5)
    if not 15 <= rounded <= 720:
        raise ModelUnavailable('预测工时超出 15–720 分钟的派单范围，请调整受理参数')
    return rounded
