import torch
import torch.nn as nn
import torch.nn.functional as f
import numpy as np
import math

class TransEncoder(nn.Module):
    def __init__(self, n_xdims, nhead, num_layers):
        super(TransEncoder, self).__init__()
        self.encoder_layer = nn.TransformerEncoderLayer(n_xdims, nhead, 128)
        self.transformer_encoder = nn.TransformerEncoder(self.encoder_layer, num_layers)

    def forward(self, inputs):
        out = self.transformer_encoder(inputs)
        return out

class SingleLayerDecoder(nn.Module):
    def __init__(self, n_xdims, decoder_hidden_dim, node_num):
        super(SingleLayerDecoder, self).__init__()

        self.max_length = node_num

        self.fc_l = nn.Linear(n_xdims, decoder_hidden_dim, bias=True)
        self.fc_r = nn.Linear(n_xdims, decoder_hidden_dim, bias=True)
        self.fc_3 = nn.Linear(decoder_hidden_dim, 1, bias=True)
        # self.fc_l = nn.Linear(n_xdims, decoder_hidden_dim)
        # self.fc_r = nn.Linear(n_xdims, decoder_hidden_dim)
        # self.fc_3 = nn.Linear(decoder_hidden_dim, 1)
        # self.tanh_ = f.tanh()
        self.init_weights()

    def init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight.data)
                m.bias.data.fill_(0.0)
            elif isinstance(m, nn.BatchNorm1d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def forward(self, input):
        dot_l = self.fc_l(input) # bz, num, dim
        dot_r = self.fc_r(input)
        tiled_l = dot_l.unsqueeze(2).repeat(1, 1, dot_l.shape[1], 1) # bz, num, num, dim
        tiled_r = dot_r.unsqueeze(1).repeat(1, dot_r.shape[1], 1, 1)
        # final_sum = torch.tanh(tiled_l + tiled_r)
        # final_sum = tiled_l + tiled_r
        final_sum = torch.relu(tiled_l + tiled_r)
        logits = torch.sigmoid(self.fc_3(final_sum).squeeze(-1))

        self.adj_prob = logits  # probs input probability, logit input log_probability # 64.12

        self.samples = []
        self.mask_scores = []
        self.entropy = []

        for i in range(self.max_length):
            position = torch.ones([input.shape[0]]) * i
            position = position.long()

            # Update mask
            self.mask = 1 - f.one_hot(position, num_classes=self.max_length)
            masked_score = self.adj_prob[:, i, :] * self.mask  #  logit : input log_probability # 64.12

            prob = torch.distributions.Bernoulli(masked_score)
            sampled_arr = prob.sample()
            self.samples.append(sampled_arr)
            self.mask_scores.append(masked_score)
            # self.exp_mask_scores.append(torch.exp(masked_score))
            self.entropy.append(prob.entropy())

        return self.samples, self.mask_scores, self.entropy, self.adj_prob

class Actor_graph(nn.Module):
    def __init__(self, args):
        super(Actor_graph, self).__init__()
        self.n_xdims = args.n_xdims
        self.nhead = args.nhead
        self.num_layers = args.num_layers
        self.decoder_hidden_dim = args.decoder_hidden_dim
        self.node_num = args.n_agents
        self.avg_baseline = -1

        self.encoder = TransEncoder(self.n_xdims, self.nhead, self.num_layers)
        self.decoder = SingleLayerDecoder(self.n_xdims, self.decoder_hidden_dim, self.node_num)

    def forward(self, src):
        encoder_output = self.encoder(src)  # 25.5.40
        samples, mask_scores, entropy, adj_prob = self.decoder(encoder_output)
        graphs_gen = torch.stack(samples).permute(1, 0, 2) # 1.3.3
        # graph_batch = torch.mean(graphs_gen, dim=0) # 3.3
        logits_for_rewards = torch.stack(mask_scores).permute(1, 0, 2)  # 1.3.3
        log_softmax_logits_for_rewards = f.log_softmax(logits_for_rewards)  # 1.3.3
        # log_prob_for_rewards = torch.log(adj_prob) * (1-torch.eye(self.node_num)) # 1.3.3

        entropy_for_rewards = torch.stack(entropy).permute(1, 0, 2) # 1.3.3
        entropy_regularization = torch.mean(entropy_for_rewards, dim=[1, 2])

        return encoder_output, samples, mask_scores, entropy, adj_prob, log_softmax_logits_for_rewards, entropy_regularization

class Critic_graph(nn.Module):
    def __init__(self, args):
        super(Critic_graph, self).__init__()
        self.n_xdims = args.n_xdims
        self.num_neurons = args.critic_hidden_dim
        self.fc_1 = nn.Linear(self.n_xdims, self.num_neurons)
        self.fc_2 = nn.Linear(self.num_neurons, 1, bias=True)
        self.init_weights()

    def init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight.data)
                m.bias.data.fill_(0.0)
            elif isinstance(m, nn.BatchNorm1d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def predict_rewards(self, encoder_output):
        # [Batch size, Sequence Length, Num_neurons] to [Batch size, Num_neurons]
        frame = torch.mean(encoder_output, 1) # 5.3.8  -->  5.8
        # ffn 1   # 5.8 --> 8.8
        h0 = torch.relu(self.fc_1(frame))
        # ffn 2
        self.predictions = self.fc_2(h0).squeeze(-1)

        return self.predictions


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    args.n_xdims = 8
    args.nhead = 4
    args.num_layers = 2
    args.decoder_hidden_dim = 16
    args.node_num = 3
    args.critic_hidden_dim = 16

    src = torch.rand(5, 3, 8)

    actor = Actor_graph(args)
    encoder_output, samples, mask_scores, entropy,\
    log_softmax_logits_for_rewards, entropy_regularization =actor(src)

    critic = Critic_graph(args)
    pre = critic.predict_rewards(encoder_output)   ### avg_baseline???













