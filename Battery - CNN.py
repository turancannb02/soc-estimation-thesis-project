# -*- coding: utf-8 -*-
"""Battery - CNN - 20240429.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1G8jF2QHdRCGxts0fE8R3JbMkVzjYwwhQ

#CNN - 20240429
"""

import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
import sys

# Dataset yolunu ayarlıyorum
sys.path.append('/content/drive/MyDrive/BATTERY DATASET - GITHUB/TEC-reduced-model-main/tec_reduced_model')
from process_experimental_data import import_thermal_data

# Verileri yüklüyorum
T_values = [0, 10, 25]
Crates_values = [0.1, 0.5, 1, 2]
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
            print(f"C-rate {Crate}, Sıcaklık {T} için veri işleme hatası: {e}")

# Verileri seçip sıralıyorum
selected_columns = ["Voltage [V]", "Current [A]", "AhAccu [Ah]", "WhAccu [Wh]", "Watt [W]", "Temp Cell [degC]"]
all_data_updated = all_data[selected_columns].astype(float)
column_to_move = 'AhAccu [Ah]'
column_series = all_data_updated.pop(column_to_move)
all_data_updated[column_to_move] = column_series
all_data_updated_train = all_data_updated[:1053529]
all_data_updated_test = all_data_updated[1053529:]

# Model parametrelerini belirliyorum
n_features = len(all_data_updated_train.columns) - 1  # Hedef değişken hariç özellik sayısı
n_targets = 1  # 'AhAccu [Ah]' tahmin ediliyor
sequence_length = 10  # Girdi dizisinin uzunluğu
batch_size = 128
epochs = 5
learning_rate = 0.0001

# Verileri hazırlıyorum
X_train = all_data_updated_train.iloc[:, :-1].values
y_train = all_data_updated_train.iloc[:, -1].values
X_test = all_data_updated_test.iloc[:, :-1].values
y_test = all_data_updated_test.iloc[:, -1].values

# Verileri standartlaştırıyorum
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Sekansları oluşturuyorum
def create_sequences(data, seq_length):
    sequences = []
    for i in range(len(data) - seq_length + 1):
        sequence = data[i:i+seq_length]
        sequences.append(sequence)
    return np.array(sequences)

X_train_seq = create_sequences(X_train_scaled, sequence_length)
X_test_seq = create_sequences(X_test_scaled, sequence_length)

# Tensörlere dönüştürüyorum
X_train_tensor = torch.Tensor(X_train_seq)
y_train_tensor = torch.Tensor(y_train[sequence_length-1:]).unsqueeze(1)
X_test_tensor = torch.Tensor(X_test_seq)
y_test_tensor = torch.Tensor(y_test[sequence_length-1:]).unsqueeze(1)

# Veri kümeleri ve veri yükleyicileri oluşturuyorum
train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=batch_size)

# Dikkat mekanizmasını tanımlıyorum
class Attention(nn.Module):
    def __init__(self, input_dim):
        super(Attention, self).__init__()
        self.attention_weights = nn.Linear(input_dim, 1, bias=False)

    def forward(self, x):
        attention_scores = self.attention_weights(x)
        attention_weights = torch.softmax(attention_scores, dim=1)
        context_vector = torch.sum(attention_weights * x, dim=1)
        return context_vector, attention_weights

# CNN modelini tanımlıyorum
class CNNRegressor(nn.Module):
    def __init__(self, n_features, seq_length, n_targets):
        super(CNNRegressor, self).__init__()
        self.relu = nn.ReLU()  # Define relu first
        self.conv1 = nn.Conv1d(n_features, 32, kernel_size=3)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=3)
        self.maxpool = nn.MaxPool1d(kernel_size=2)

        # Calculate the correct input dimension for fc1 layer
        conv_output_size = self._get_conv_output_size(n_features, seq_length)
        self.fc1 = nn.Linear(conv_output_size, 128)
        self.fc2 = nn.Linear(128, n_targets)

    def _get_conv_output_size(self, n_features, seq_length):
        # Temporary tensor to calculate convolution output size
        temp_input = torch.zeros(1, n_features, seq_length)
        output = self.maxpool(self.relu(self.conv1(temp_input)))
        output = self.maxpool(self.relu(self.conv2(output)))
        n_size = output.data.view(1, -1).size(1)
        return n_size

    def forward(self, x):
        x = x.transpose(1, 2)  # CNN expects channels first
        x = self.relu(self.conv1(x))
        x = self.maxpool(x)
        x = self.relu(self.conv2(x))
        x = self.maxpool(x)
        x = x.view(x.size(0), -1)  # Flatten the tensor
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        return x

from sklearn.metrics import mean_squared_error

# Modeli oluşturuyorum ve eğitim parametrelerini belirliyorum
model = CNNRegressor(n_features, sequence_length, n_targets)
criterion = nn.MSELoss()  # Hata ölçümü için MSE kullanıyorum
optimizer = torch.optim.RMSprop(model.parameters(), lr=learning_rate, weight_decay=1e-5, momentum=0.9)

# Modeli eğitiyorum
for epoch in range(epochs):
    train_loss = 0
    model.train()
    for inputs, targets in train_loader:
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()
        train_loss += loss.item()

    train_loss /= len(train_loader)

    model.eval()
    test_loss = 0
    with torch.no_grad():
        for inputs, targets in test_loader:
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            test_loss += loss.item()
    test_loss /= len(test_loader)

    print(f"Epoch [{epoch+1}/{epochs}], Train Loss: {train_loss}, Test Loss: {test_loss}")

import matplotlib.pyplot as plt
import seaborn as sns

# Dikkat ağırlıklarını görselleştiriyorum
attention_weights = np.random.rand(5, 5)  # Bu değerler modelinizden alınmalıdır

plt.figure(figsize=(10, 8))
sns.heatmap(attention_weights, annot=True, cmap='Reds')
plt.title('Attention Weights')
plt.xlabel('Sequence Position')
plt.ylabel('Sequence Position')
plt.show()

model.eval()
with torch.no_grad():
    example_input = X_test_tensor[0].unsqueeze(0)  # 1 örnek seç
    _, attention_weights = model(example_input)

attention_weights_np = attention_weights.squeeze().cpu().numpy()
print("Attention Ağırlıkları (Şekil):", attention_weights_np.shape)
print("Attention Ağırlıkları:", attention_weights_np)

# Attention ağırlıklarını yazdırma
attention_weights_df = pd.DataFrame(attention_weights_np, columns=["Ağırlık"])
print("Attention Ağırlıkları (DataFrame):")
print(attention_weights_df)

import matplotlib.pyplot as plt
import seaborn as sns

# Attention ağırlıklarını görselleştiriyorum
plt.figure(figsize=(10, 8))
sns.heatmap(attention_weights_np, annot=True, cmap='Reds')
plt.title('Attention Ağırlıkları')
plt.xlabel('Sıra Pozisyonu')
plt.ylabel('Sıra Pozisyonu')
plt.show()

# Eğitim veri setini pandas DataFrame'e dönüştürüyorum
train_df = pd.DataFrame(X_train_scaled, columns=["Voltage [V]", "Current [A]", "WhAccu [Wh]", "Watt [W]", "Temp Cell [degC]"])

# 'AhAccu [Ah]' sütununu ekliyorum
train_df['AhAccu [Ah]'] = y_train

# Korelasyon matrisini hesaplıyorum
corr_matrix = train_df.corr()

# Korelasyon matrisini görselleştiriyorum
plt.figure(figsize=(10, 6))
sns.heatmap(corr_matrix, annot=True, cmap='BuPu', fmt=".2f", linewidths=.5)
plt.title("Korelasyon Matrisi")
plt.show()

import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error

# Modeli değerlendiriyorum
with torch.no_grad():
    y_true_list = []
    y_pred_list = []
    test_loss = 0
    for batch in test_loader:
        inputs, targets = batch
        outputs = model(inputs)
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
    plt.title('CNN Tahminleri vs. Gerçek Veriler')
    plt.legend()
    plt.show()

# 3D plot oluşturuyorum
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

# Zaman adımlarını ve tahminleri hazırlıyorum
time_steps = np.arange(len(y_true))  # Or your specific time steps
y_true = np.array(y_true)  # Gerçek values
y_pred = np.array(y_pred)  # Predicted values

fig = plt.figure(figsize=(12, 6))
ax = fig.add_subplot(111, projection='3d')

# 3D çizim yapıyorum
ax.plot(time_steps, y_true, zs=0, zdir='z', label='Gerçek')
ax.plot(time_steps, y_pred, zs=1, zdir='z', label='Predicted')

# Etiketler ve başlıklar ekliyorum
ax.set_xlabel('Time')
ax.set_ylabel('Gerçek Value')
ax.set_zlabel('Predicted Value')
ax.legend()

# Grafiği gösteriyorum
plt.show()