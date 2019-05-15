import json
import string
import random
import sys
sys.path.append('../')
import torch
import torch.nn as nn
import numpy as np

data = []
with open('../poet.tang.20000.json', encoding='utf-8') as json_file:
  data += json.load(json_file)
with open('../poet.tang.21000.json', encoding='utf-8') as json_file:
  data += json.load(json_file)
with open('../poet.tang.22000.json', encoding='utf-8') as json_file:
  data += json.load(json_file)
with open('../poet.tang.23000.json', encoding='utf-8') as json_file:
  data += json.load(json_file)
with open('../poet.tang.24000.json', encoding='utf-8') as json_file:
  data += json.load(json_file)

paragraphs = [item['paragraphs'] for item in data]
random.shuffle(paragraphs)

#####################
# Preprocess
#####################
def get_vocab_seqs(sample_size=1000, seq_lenth=48):
  assert sample_size <= 4000
  # create vocab
  words = ['EOS', 'OOV']
  for paragraph in paragraphs[:sample_size]:
    for sentence in paragraph:
      for word in sentence:
        words.append(word)
  words = set(words)
  vocab = {word: i for i, word in enumerate(words)}
  # cut into fix length sentence
  sequences = []
  for paragraph in paragraphs[:sample_size]:
    seq = ""
    for sentence in paragraph:
      seq += sentence
      if len(seq) >= seq_lenth:
        sequences.append(seq[:seq_lenth])
        seq = ""
  # seq to int
  xs, ys = seq_to_int(vocab, sequences)
  return list(words), vocab, sequences, xs, ys  # translate words into list

def seq_to_int(vocab, sequences):
  xs = []
  ys = []
  for sequence in sequences:
    seq = []
    for word in sequence:
      if word in vocab:
        seq.append(vocab[word])
      else:
        seq.append(vocab['OOV'])
    seq_next = seq[1:]
    seq_next.append(vocab['EOS'])
    xs.append(seq)
    ys.append(seq_next)
  return xs, ys

#####################
# LSTM model
#####################
class LSTM(nn.Module):
  def __init__(self, vocab_size, input_dim, hidden_dim, batch_size, output_dim=1,
                  num_layers=2):
    super(LSTM, self).__init__()
    self.input_dim = input_dim
    self.hidden_dim = hidden_dim
    self.batch_size = batch_size
    self.num_layers = num_layers
    # Embedding fn
    self.embed = nn.Embedding(vocab_size, self.input_dim)
    # Define the LSTM layer
    self.lstm = nn.LSTM(self.input_dim, self.hidden_dim, self.num_layers)
    # Define the output layer
    self.linear = nn.Linear(self.hidden_dim, output_dim)

  def init_hidden(self):
    # This is what we'll initialise our hidden state as
    return (torch.zeros(self.num_layers, self.batch_size, self.hidden_dim),
            torch.zeros(self.num_layers, self.batch_size, self.hidden_dim))

  def forward(self, input):
    # embed input
    input = self.embed(input)
    # Forward pass through LSTM layer
    # shape of lstm_out: [input_size, batch_size, hidden_dim]
    # shape of self.hidden: (a, b), where a and b both 
    # have shape (num_layers, batch_size, hidden_dim).
    lstm_out, self.hidden = self.lstm(input.view(len(input), self.batch_size, -1))
    # linear to dim-V, then softmax
    y_pred = self.linear(lstm_out.view(len(input), self.batch_size, -1))
    # softmax
    y_pred = nn.functional.softmax(y_pred, dim=2)
    return y_pred

#####################
# Init
#####################
seq_len = 48  # 句长
sample_size = 2048  # 诗个数
words, vocab, sequences, X_int, y_int = get_vocab_seqs(sample_size, seq_len)
vocab_size = len(words)
input_dim = 256  # 单个字向量长
hidden_dim = 256
batch_size = 32
output_dim = vocab_size
num_layers = 2
model = LSTM(vocab_size=vocab_size, input_dim=input_dim, hidden_dim=hidden_dim, 
        batch_size=batch_size, output_dim=output_dim, num_layers=num_layers)
# # X_train and y_train & target
# X_transpose = np.array(X_int[:batch_size]).transpose()
# X_onehot = np.eye(input_dim)[X_transpose]
# X_train = torch.from_numpy(X_onehot).type(torch.Tensor)
# y_transpose = np.array(y_int[:batch_size]).transpose()
# y_train = torch.from_numpy(y_transpose).type(torch.LongTensor)
# target = y_train.contiguous().view(-1)
# loss_fn and optimiser
loss_fn = torch.nn.CrossEntropyLoss(reduction='sum')
learning_rate = 0.01
optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
# claim globally
X_train = []
y_train = []
hist = []
batch_start = 0

def get_var():
  return {'X': X_train, 'y': y_train, 'V': vocab, 'seq': sequences, 'm': model, 'w': words, 'h': hist}

#####################
# Trainer
#####################
def train(num_epochs):
  global hist
  hist = np.zeros(num_epochs)
  for t in range(num_epochs):
    global batch_start
    # batch_start = (batch_start + batch_size) % len(X_int)
    # 保证 l r 不会横跨末尾
    if batch_start < batch_size:
      batch_start += batch_size
    l = batch_start - batch_size
    r = batch_start
    # X_train and y_train & target
    global X_train
    global y_train
    X_transpose = np.array(X_int[l:r]).transpose()
    X_train = torch.from_numpy(X_transpose).type(torch.LongTensor)
    y_transpose = np.array(y_int[l:r]).transpose()
    y_train = torch.from_numpy(y_transpose).type(torch.LongTensor)
    target = y_train.contiguous().view(-1)
    # Clear stored gradient
    model.zero_grad()
    # Initialise hidden state
    # Don't do this if you want your LSTM to be stateful
    model.hidden = model.init_hidden()
    # Forward pass
    y_pred = model(X_train)
    # compute loss
    output = y_pred.view(-1, vocab_size)
    loss = loss_fn(output, target)
    hist[t] = loss.item()
    if t % 32 == 0:
      print("from ", l, " to ", r)
      print("Epoch ", t, "CE: ", loss.item())
      print("sample input: ", translate_int(X_int[l]))
      print("sample output: ", translate_vec(y_pred.detach().numpy().transpose().tolist()[0]))
      print(y_pred[0])
    # Zero out gradient, else they will accumulate between epochs
    optimiser.zero_grad()
    # backward
    loss.backward()
    # Update parameters
    optimiser.step()

def translate_int(sentence):  # only accept list
  seq = ""
  for idx in sentence:
    seq += words[idx]
  return seq

def translate_vec(sentence):  # only accept list
  seq = ""
  for vec in sentence:
    idx = np.argmax(vec)
    seq += words[idx]
  return seq

def generate(seed=None, length=48):
  # set up first char
  start = [[ random.randint(0, vocab_size-1) ]]
  if not seed is None:
    if seed in words:
      start = [[ vocab[seed] ]]
    else:
      start = [[ vocab['OOV'] ]]
  start = torch.LongTensor(start)
  # init hidden
  model.hidden = (torch.zeros(model.num_layers, 1, model.hidden_dim),  # batch_size is 1
                  torch.zeros(model.num_layers, 1, model.hidden_dim))
  # generate
  seq = ""
  seq += translate_int(start.numpy().tolist()[0])
  for i in range(length):
    start = model.embed(start)
    lstm_out, model.hidden = model.lstm(start.view(1, 1, -1))  # seq_len=1, batch_size=1
    y_pred = model.linear(lstm_out.view(1, 1, -1))
    y_pred = nn.functional.softmax(y_pred, dim=2)
    # get next
    print(y_pred[0])
    next_char = translate_vec(y_pred.detach().numpy().transpose().tolist()[0])
    seq += next_char
    start = torch.LongTensor([[ vocab[next_char] ]])
  print(seq)

# >>> target = torch.empty(1, dtype=torch.long).random_(10)
# >>> target
# tensor([9])
# >>> loss_fn(y_pred[0], target)
# tensor(2.3179, grad_fn=<NllLossBackward>)