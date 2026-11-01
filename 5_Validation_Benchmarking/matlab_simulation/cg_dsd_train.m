function cg_dsd_train
% CG_DSD_TRAIN  Trains the driving policy (Deep Learning Toolbox) on the expert data and exports it for the Simulink model.
%   features (11): lane offset error, heading error, road curvature, speed, speed error, planned accel, hazard-active flag,
%                  lane offset and heading error of the previous two 0.1 s steps
%   outputs  (2): steering angle [rad], acceleration command [m/s^2]  (expert = LKA MPC block + PID block)
%   Network 11-64-64-2, ReLU. Runs whose lane keeping failed are dropped. Every 5th run is held out for validation.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
files = dir(fullfile('results', 'dsd_data', 'run_*.mat'));
X = [];  Y = [];  G = [];  nbad = 0;
for k = 1:numel(files)
    S = load(fullfile(files(k).folder, files(k).name));
    m = S.metrics;
    if isfield(m, 'lat_err_pre'), settled = m.lat_err_pre; else, settled = m.max_lat_err_before - abs(S.o.e1_0); end     % judged after the start error has been corrected
    why = '';
    if settled > 0.3, why = sprintf('lane error after start correction %.2f m', settled);
    elseif S.o.shoulder && ~m.in_shoulder, why = sprintf('did not reach the shoulder (end %.2f m)', m.lat_end);
    elseif any(~isfinite(S.F(:))), why = 'NaN in data'; end
    if ~isempty(why), nbad = nbad + 1;  fprintf('  dropped %s: v0 %.1f, Rmin %.0f, %s\n', files(k).name, S.o.v0, S.o.Rmin, why); continue, end
    X = [X; S.F]; Y = [Y; S.Tg]; G = [G; k * ones(size(S.F, 1), 1)]; %#ok<AGROW>
end
fprintf('%d runs used, %d dropped, %d samples.\n', numel(unique(G)), nbad, size(X, 1));
if size(X, 1) < 500, error('Not enough data. Run cg_dsd_collect first.'); end
isval = mod(G, 5) == 0;
mu_in = mean(X(~isval, :))';  sd_in = std(X(~isval, :))';  sd_in(sd_in < 1e-6) = 1;
mu_out = mean(Y(~isval, :))'; sd_out = std(Y(~isval, :))'; sd_out(sd_out < 1e-6) = 1;
Xn = (X - mu_in') ./ sd_in';  Yn = (Y - mu_out') ./ sd_out';
layers = [featureInputLayer(11, 'Normalization', 'none'); fullyConnectedLayer(64); reluLayer; fullyConnectedLayer(64); reluLayer; fullyConnectedLayer(2)];
opts = trainingOptions('adam', 'MaxEpochs', 80, 'MiniBatchSize', 256, 'InitialLearnRate', 3e-3, 'LearnRateSchedule', 'piecewise', ...
    'LearnRateDropPeriod', 25, 'LearnRateDropFactor', 0.3, 'Shuffle', 'every-epoch', 'ValidationData', {Xn(isval, :), Yn(isval, :)}, ...
    'ValidationFrequency', 100, 'Verbose', true, 'VerboseFrequency', 100, 'Plots', 'none', 'ExecutionEnvironment', 'cpu');
net = trainnet(Xn(~isval, :), Yn(~isval, :), layers, 'mse', opts);
L = net.Layers;  fc = L(arrayfun(@(l) isa(l, 'nnet.cnn.layer.FullyConnectedLayer'), L));
num = @(x) double(gather(plainArray(x)));
cg_nn = struct('W1', num(fc(1).Weights), 'b1', num(fc(1).Bias(:)), ...
               'W2', num(fc(2).Weights), 'b2', num(fc(2).Bias(:)), ...
               'W3', num(fc(3).Weights), 'b3', num(fc(3).Bias(:)), ...
               'mu_in', mu_in, 'isd_in', 1 ./ sd_in, 'sd_out', sd_out, 'mu_out', mu_out);
save(fullfile('results', 'dsd_nn.mat'), 'cg_nn');
% check the exported weights reproduce the network and report errors in physical units
P = @(x) (max(0, max(0, ((x - mu_in') ./ sd_in') * cg_nn.W1' + cg_nn.b1') * cg_nn.W2' + cg_nn.b2') * cg_nn.W3' + cg_nn.b3') .* sd_out' + mu_out';
Pv = P(X(isval, :));  Ev = Pv - Y(isval, :);
fprintf('\nValidation (held-out runs, %d samples):\n', nnz(isval));
fprintf('  steering : RMS error %.3f deg   (spread of expert steering: %.2f deg)\n', rad2deg(rms(Ev(:,1))), rad2deg(std(Y(isval,1))));
fprintf('  accel    : RMS error %.3f m/s^2 (spread of expert accel: %.2f m/s^2)\n', rms(Ev(:,2)), std(Y(isval,2)));
f = figure('Visible', 'off', 'Position', [50 50 1100 450]);
subplot(1,2,1); plot(rad2deg(Y(isval,1)), rad2deg(Pv(:,1)), '.'); grid on; xlabel('expert steering (deg)'); ylabel('network (deg)'); title('Steering, held-out runs'); axis equal
subplot(1,2,2); plot(Y(isval,2), Pv(:,2), '.'); grid on; xlabel('expert accel (m/s^2)'); ylabel('network (m/s^2)'); title('Acceleration, held-out runs'); axis equal
exportgraphics(f, fullfile('results', 'dsd_train.png'), 'Resolution', 110);  close(f);
fprintf('Saved results/dsd_nn.mat and results/dsd_train.png\n');
end

function x = plainArray(x)
if isa(x, 'dlarray'), x = extractdata(x); end
end
