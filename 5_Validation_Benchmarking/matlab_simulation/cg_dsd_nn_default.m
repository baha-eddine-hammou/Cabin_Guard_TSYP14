function nn = cg_dsd_nn_default
% CG_DSD_NN_DEFAULT  Placeholder network (11 inputs - 64 - 64 - 2 outputs, all zero) so the model can be built before training.
nn = struct('W1', zeros(64, 11), 'b1', zeros(64, 1), 'W2', zeros(64, 64), 'b2', zeros(64, 1), 'W3', zeros(2, 64), 'b3', zeros(2, 1), ...
            'mu_in', zeros(11, 1), 'isd_in', ones(11, 1), 'sd_out', ones(2, 1), 'mu_out', zeros(2, 1));
end
