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


class ModelUnavailable(ValueError):
    pass


def vector(row):
    return [float(row[key]) for key in FEATURES]


def fit(history, order, technician):
    if len(history) < MIN_HISTORY:
        raise ModelUnavailable(f'同类完单历史至少需要 {MIN_HISTORY} 条，目前 {len(history)} 条')
    # Hold out entire appointment days. The newest date in training predates validation.
    split_date = history[int(len(history) * 0.8)]['service_date']
    train = [row for row in history if row['service_date'] < split_date]
    test = [row for row in history if row['service_date'] >= split_date]
    if len(train) < 20 or len(test) < 6:
        raise ModelUnavailable('历史完单分布过于集中，无法按日期切分训练与验证集')
    x_train = np.array([vector(row) for row in train])
    y_train = np.array([row['actual_minutes'] for row in train])
    x_test = np.array([vector(row) for row in test])
    y_test = np.array([row['actual_minutes'] for row in test])
    scaler = StandardScaler().fit(x_train)
    lasso = Lasso(alpha=ALPHA, max_iter=5000, tol=1e-7).fit(scaler.transform(x_train), y_train)
    selected = np.abs(lasso.coef_) > 1e-7
    if not selected.any():
        raise ModelUnavailable('Lasso 未保留任何特征，无法出具派单解释')
    linear = LinearRegression().fit(x_train[:, selected], y_train)
    if linear.rank_ != int(selected.sum()):
        raise ModelUnavailable('入选特征的历史样本共线，无法解释回归系数')
    actual_input = vector({**order, 'experience_years': technician['experience_years']})
    means = x_train.mean(axis=0)
    ranges = zip(x_train.min(axis=0), x_train.max(axis=0))
    weights = np.zeros(len(FEATURES))
    weights[selected] = linear.coef_
    contributions = weights * (np.array(actual_input) - means)
    center = float(linear.intercept_ + np.dot(weights, means))
    fingerprint_fields = [[row['id'], str(row['service_date']), vector(row), row['actual_minutes']]
                          for row in history]
    fingerprint = hashlib.sha256(json.dumps(fingerprint_fields, separators=(',', ':')).encode()).hexdigest()
    return {
        'alpha': ALPHA, 'history_count': len(history), 'train_count': len(train), 'test_count': len(test),
        'history_checksum': fingerprint, 'holdout_since': str(split_date),
        'holdout_mae': round(float(mean_absolute_error(y_test, linear.predict(x_test[:, selected]))), 2),
        'training_mean_minutes': center, 'certificate': technician['certificate'],
        'features': [
            {'key': key, 'selected': bool(selected[i]), 'lasso_weight': float(lasso.coef_[i]),
             'coefficient': float(weights[i]), 'training_mean': float(means[i]), 'value': actual_input[i],
             'contribution': float(contributions[i]), 'training_min': float(low), 'training_max': float(high),
             'outside_history': not low <= actual_input[i] <= high}
            for i, (key, (low, high)) in enumerate(zip(FEATURES, ranges))
        ],
    }


def estimate(analysis):
    raw = analysis['training_mean_minutes'] + sum(feature['contribution'] for feature in analysis['features'])
    rounded = math.floor(raw + 0.5)
    if not 15 <= rounded <= 720:
        raise ModelUnavailable('预测工时超出 15–720 分钟的派单范围，请调整受理参数')
    return rounded
