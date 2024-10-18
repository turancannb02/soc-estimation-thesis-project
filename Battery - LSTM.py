# -*- coding: utf-8 -*-
"""Battery - LSTM_v1.2 - 20240525.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1rs1RmEAhNClg7ZmhxkxVrCHDRCWoDk5z

# Battery - LSTM_v1.2 - 20240525
"""

# Optuna kütüphanesini yüklüyorum
!pip install optuna

import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
import sys
import optuna
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt

# Dataset yolunu ayarlıyorum
sys.path.append('/content/drive/MyDrive/BATTERY DATASET - GITHUB/TEC-reduced-model-main/tec_reduced_model')
from process_experimental_data import import_thermal_data

# Verileri yüklüyorum
T_values = [0, 10, 25]
Crates_values = [0.5, 1, 2]
all_data = pd.DataFrame()

# Her bir sıcaklık ve Crate değeri için verileri import ediyorum ve birleştiriyorum
for T in T_values:
    for Crate in Crates_values:
        try:
            cell_data_dict = import_thermal_data(Crate, T)
            for cell_id, df in cell_data_dict.items():
                selected_columns = ["Voltage [V]", "Current [A]", "AhAccu [Ah]", "WhAccu [Wh]", "Watt [W]", "Temp Cell [degC]", "Time [s]"]
                df = df[selected_columns].astype(float)
                all_data = pd.concat([all_data, df])
        except ValueError as e:
            print(f"Error processing data for C-rate {Crate}, Temperature {T}: {e}")

# Veri ön işleme
selected_columns = ["Voltage [V]", "Current [A]", "AhAccu [Ah]", "WhAccu [Wh]", "Watt [W]", "Temp Cell [degC]"]
all_data_updated = all_data[selected_columns].astype(float)

# 'AhAccu [Ah]' sütununu sona taşıyorum
column_to_move = 'AhAccu [Ah]'
column_series = all_data_updated.pop(column_to_move)
all_data_updated[column_to_move] = column_series

# Veriyi eğitim ve test olarak bölüyorum
train_size = int(0.8 * len(all_data_updated))
all_data_updated_train = all_data_updated[:train_size]
all_data_updated_test = all_data_updated[train_size:]

# Veriyi standartlaştırıyorum
scaler = StandardScaler()
X_train = scaler.fit_transform(all_data_updated_train.iloc[:, :-1])
y_train = all_data_updated_train.iloc[:, -1].values
X_test = scaler.transform(all_data_updated_test.iloc[:, :-1])
y_test = all_data_updated_test.iloc[:, -1].values

# Sekanslar oluşturuyorum
sequence_length = 5
def create_sequences(X, y, seq_length):
    X_seq, y_seq = [], []
    for i in range(len(X) - seq_length):
        X_seq.append(X[i: i + seq_length])
        y_seq.append(y[i + seq_length - 1])
    return np.array(X_seq), np.array(y_seq)

X_train_seq, y_train_seq = create_sequences(X_train, y_train, sequence_length)
X_test_seq, y_test_seq = create_sequences(X_test, y_test, sequence_length)

# Tensörlere dönüştürüyorum ve DataLoader oluşturuyorum
train_batch_size = 256
test_batch_size = 128
train_dataset = TensorDataset(torch.Tensor(X_train_seq), torch.Tensor(y_train_seq).unsqueeze(1))
test_dataset = TensorDataset(torch.Tensor(X_test_seq), torch.Tensor(y_test_seq).unsqueeze(1))
train_loader = DataLoader(train_dataset, batch_size=train_batch_size, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=test_batch_size)

# LSTM modelini tanımlıyorum
class LSTMRegressor(nn.Module):
    def __init__(self, n_features, n_targets, n_hidden, n_layers, dropout):
        super(LSTMRegressor, self).__init__()
        self.lstm = nn.LSTM(n_features, n_hidden, n_layers, dropout=dropout if n_layers > 1 else 0, batch_first=True)
        self.fc = nn.Linear(n_hidden, n_targets)

    def forward(self, x):
        output, _ = self.lstm(x)
        x = output[:, -1, :]
        x = self.fc(x)
        return x

# Hyperparameter Tuning with Optuna
def objective(trial):
    n_hidden = trial.suggest_int('n_hidden', 32, 64)
    n_layers = trial.suggest_int('n_layers', 1, 3)
    dropout = trial.suggest_float('dropout', 0.1, 0.3)
    learning_rate = trial.suggest_float('learning_rate', 1e-4, 1e-3)

    model = LSTMRegressor(n_features=5, n_targets=1, n_hidden=n_hidden, n_layers=n_layers, dropout=dropout)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    num_epochs = 3  # Reduce the number of epochs for faster trials
    for epoch in range(num_epochs):
        model.train()
        total_loss = 0
        for data, target in train_loader:
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item()

        model.eval()
        test_loss = 0
        with torch.no_grad():
            for data, target in test_loader:
                output = model(data)
                test_loss += criterion(output, target).item()
        test_loss /= len(test_loader)

    return test_loss

# Optuna çalışmasını başlatıyorum
study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=20)

# En iyi model parametreleri ile modeli eğitiyorum
best_params = study.best_params
learning_rate = best_params.pop('learning_rate')
best_model = LSTMRegressor(n_features=5, n_targets=1, **best_params)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(best_model.parameters(), lr=learning_rate)

num_epochs = 15  # Modeli daha uzun süre eğitmek için epoch sayısını artırıyorum
train_losses = []
test_losses = []

for epoch in range(num_epochs):
    best_model.train()
    total_loss = 0
    for data, target in train_loader:
        optimizer.zero_grad()
        output = best_model(data)
        loss = criterion(output, target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(best_model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()
    train_loss = total_loss / len(train_loader)
    train_losses.append(train_loss)

    best_model.eval()
    test_loss = 0
    with torch.no_grad():
        y_true_list = []
        y_pred_list = []
        for data, target in test_loader:
            output = best_model(data)
            test_loss += criterion(output, target).item()
            y_true_list.extend(target.detach().numpy())
            y_pred_list.extend(output.detach().numpy())
    test_loss /= len(test_loader)
    test_losses.append(test_loss)

    print(f"Epoch [{epoch+1}/{num_epochs}], Train Loss: {train_loss}, Test Loss: {test_loss}")

# Modeli değerlendiriyorum
with torch.no_grad():
    y_true_list = []
    y_pred_list = []
    test_loss = 0
    for batch in test_loader:
        inputs, targets = batch
        outputs = best_model(inputs)
        loss = criterion(outputs, targets)
        test_loss += loss.item()
        y_true_list.extend(targets.detach().cpu().numpy())
        y_pred_list.extend(outputs.detach().cpu().numpy())

    y_pred = np.array(y_pred_list)
    y_true = np.array(y_true_list)
    average_test_loss = test_loss / len(test_loader)
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)

    print(f"Average Test Loss: {average_test_loss}")
    print(f"Mean Squared Error (MSE): {mse}")
    print(f"Root Mean Squared Error (RMSE): {rmse}")

    # Tahminler ve gerçek değerleri görselleştiriyorum
    plt.figure(figsize=(10, 6))
    plt.plot(y_true, label='Gerçek')
    plt.plot(y_pred, label='Tahmin')
    plt.xlabel('Zaman')
    plt.ylabel('SoC')
    plt.title('LSTM Tahminleri vs. Gerçek Veriler')
    plt.legend()
    plt.show()

# Eğitim veri setini pandas DataFrame'e dönüştürüyorum
train_df = pd.DataFrame(X_train, columns=["Voltage [V]", "Current [A]", "WhAccu [Wh]", "Watt [W]", "Temp Cell [degC]"])

# 'AhAccu [Ah]' sütununu ekliyorum
train_df['AhAccu [Ah]'] = y_train

# Korelasyon matrisini hesaplıyorum
corr_matrix = train_df.corr()

# Korelasyon matrisini görselleştiriyorum
plt.figure(figsize=(10, 6))
sns.heatmap(corr_matrix, annot=True, cmap='BuPu', fmt=".2f", linewidths=.5)
plt.title("Korelasyon Matrisi")
plt.show()
