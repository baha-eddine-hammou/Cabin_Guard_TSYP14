function cg_dsd_report
% CG_DSD_REPORT  Paper figures and tables from the saved result files (no simulation is run).
%   Reads  results/dsd_batch.csv  (in-lane stop vs shoulder stop, close follower)
%          results/dsd_eval2.csv  (expert vs learned driver, random roads)
%          results/dsd_train.png  (copied)
%   Writes results/paper/fig_batch.png, fig_learning.png, fig_stress.png, tables.md
here = fileparts(mfilename('fullpath'));  cd(here);
out = fullfile('results', 'paper');  if ~isfolder(out), mkdir(out); end
md = {'# CabinGuard-ADI - Driving Scenario Designer closed-loop results (simulation only)', ''};
fs = 11;

%% 1. in-lane stop versus shoulder stop (close scripted follower)
if isfile(fullfile('results', 'dsd_batch.csv'))
    T = readtable(fullfile('results', 'dsd_batch.csv'));
    lab = unique(strcat(string(T.road), " ", string(T.seed)), 'stable');
    inl = strcmp(string(T.mode), 'in lane');  shd = strcmp(string(T.mode), 'shoulder');
    f = figure('Visible', 'off', 'Position', [50 50 1100 420]);  tl = tiledlayout(f, 1, 3, 'TileSpacing', 'compact');
    nexttile;  bar(categorical(lab, lab), [T.impact_ms(inl) T.impact_ms(shd)]);  grid on;  ylabel('impact speed of follower (m/s)');
    title('Rear-end impact speed');  legend('stop in lane', 'stop on shoulder', 'Location', 'northoutside');  set(gca, 'FontSize', fs);
    nexttile;  bar(categorical(lab, lab), [T.min_gap_m(inl) T.min_gap_m(shd)]);  grid on;  ylabel('smallest centre distance (m)');
    title('Closest approach (4.7 m = contact)');  yline(4.7, 'r--');  set(gca, 'FontSize', fs);
    nexttile;  bar(categorical(lab, lab), [T.stop_dist_m(inl) T.stop_dist_m(shd)]);  grid on;  ylabel('stopping distance after hazard (m)');
    title('Stopping distance');  set(gca, 'FontSize', fs);
    title(tl, 'Same ego, same follower, same roads: stopping in the lane vs on the shoulder (simulation)');
    exportgraphics(f, fullfile(out, 'fig_batch.png'), 'Resolution', 200);  close(f);
    md = [md, {'## Stop in lane vs stop on shoulder (follower 12 m behind, reacts after 2.5 s, scripted)', '', ...
        '| mode | runs | collisions | mean impact (m/s) | mean stop distance (m) |', '|---|---|---|---|---|'}];
    for k = {'in lane', 'shoulder'}
        q = strcmp(string(T.mode), k{1});
        md{end+1} = sprintf('| %s | %d | %d | %.1f | %.1f |', k{1}, nnz(q), nansum(T.collision(q)), mean(T.impact_ms(q), 'omitnan'), mean(T.stop_dist_m(q), 'omitnan')); %#ok<AGROW>
    end
    md = [md, {'', 'Caveat: one longitudinal scenario, scripted (non-reactive) follower passing about 0.4 m beside the stopped ego in the shoulder case.', ''}];
else
    fprintf('dsd_batch.csv not found - skipped figure 1\n');
end

%% 2. learned driver vs expert
if isfile(fullfile('results', 'dsd_eval2.csv'))
    E = readtable(fullfile('results', 'dsd_eval2.csv'));
    E.Properties.VariableNames{1} = 'caseno';      % first column is the case number ('case' is a MATLAB keyword, readtable renames it)
    ok = logical(E.ok);  grp = string(E.group);  drv = string(E.driver);
    cases = unique(E.caseno);
    P = nan(numel(cases), 6);   % lane err exp, net ; end lat exp, net ; stop dist exp, net
    G = strings(numel(cases), 1);
    for i = 1:numel(cases)
        a = E.caseno == cases(i) & drv == "expert";  b = E.caseno == cases(i) & drv == "network";
        if any(a) && any(b)
            P(i, :) = [E.lane_err_m(a) E.lane_err_m(b) E.lat_end_m(a) E.lat_end_m(b) E.stop_dist_m(a) E.stop_dist_m(b)];
            G(i) = grp(find(a, 1));
        end
    end
    nrm = G == "normal";  str = G == "stress";
    f = figure('Visible', 'off', 'Position', [50 50 1200 400]);  tl = tiledlayout(f, 1, 3, 'TileSpacing', 'compact');
    nexttile;  hold on;
    gl = {'normal', 'stress'};  dl = ["expert" "network"];  rate = zeros(2, 2);
    for g = 1:2
        for d = 1:2
            q = grp == gl{g} & drv == dl(d);  rate(g, d) = 100 * mean(ok(q));
        end
    end
    b = bar(categorical([sprintf("normal (%d)", nnz(grp == "normal" & drv == "expert")) sprintf("stress (%d)", nnz(grp == "stress" & drv == "expert"))]), rate);  grid on;  ylabel('successful runs (%)');  ylim([0 105]);
    legend('expert (MPC + PID)', 'learned (network)', 'Location', 'southoutside');  title('Success rate');  set(gca, 'FontSize', fs);  %#ok<NASGU>
    nexttile;  hold on;
    floor0 = 1e-3;
    loglog(max(P(nrm,1), floor0), max(P(nrm,2), floor0), 'bo', 'MarkerFaceColor', 'b');
    loglog(max(P(str,1), floor0), max(P(str,2), floor0), 'rs', 'MarkerFaceColor', 'r');
    lim = [floor0 10];  plot(lim, lim, 'k--');  xlim(lim);  ylim(lim);  grid on;  axis square;
    xlabel('expert: settled lane error (m)');  ylabel('network: settled lane error (m)');  title('Lane keeping, same case');  legend('normal', 'stress', 'Location', 'southeast');  set(gca, 'FontSize', fs);
    nexttile;  hold on;
    plot(P(nrm,3), P(nrm,4), 'bo', 'MarkerFaceColor', 'b');  plot(P(str,3), P(str,4), 'rs', 'MarkerFaceColor', 'r');
    lim = [-6 6];  plot(lim, lim, 'k--');  xlim(lim);  ylim(lim);  grid on;  axis square;
    xlabel('expert: final lateral position (m)');  ylabel('network: final lateral position (m)');  title('End position (-3.6 = shoulder, 0 = lane)');  set(gca, 'FontSize', fs);
    title(tl, 'Learned driver vs the controller it imitates, random roads (simulation)');
    exportgraphics(f, fullfile(out, 'fig_learning.png'), 'Resolution', 200);  close(f);
    md = [md, {'## Learned driver vs expert (random roads, speeds 9-20 m/s, radius 150-450 m; stress = faster/tighter)', '', ...
        '| group | driver | runs | successful | mean settled lane error (m) | mean stop distance (m) |', '|---|---|---|---|---|---|'}];
    for g = gl
        for d = ["expert" "network"]
            q = grp == g{1} & drv == d;
            md{end+1} = sprintf('| %s | %s | %d | %d | %.3f | %.1f |', g{1}, d, nnz(q), nnz(ok(q)), mean(E.lane_err_m(q), 'omitnan'), mean(E.stop_dist_m(q), 'omitnan')); %#ok<AGROW>
        end
    end
    bad = E(~ok, :);
    if ~isempty(bad)
        md = [md, {'', 'Failed runs (these are the limits):', ''}];
        for i = 1:height(bad)
            md{end+1} = sprintf('- case %d, %s, %s: v0 %.1f m/s, radius %.0f m, settled lane error %.2f m, end position %.2f m', bad.caseno(i), string(bad.group(i)), string(bad.driver(i)), bad.v0(i), bad.Rmin(i), bad.lane_err_m(i), bad.lat_end_m(i)); %#ok<AGROW>
        end
    end
    md = [md, {'', 'The network imitates the expert, so it cannot do better than the expert; outside the trained range it degrades.', ''}];
    % stress cases: where each driver fails
    if any(str)
        f = figure('Visible', 'off', 'Position', [50 50 700 420]);  hold on;
        sc = E(grp == "stress", :);
        for i = 1:height(sc)
            mk = 'o';  if string(sc.driver(i)) == "network", mk = 's'; end
            col = [0 0.6 0];  if ~logical(sc.ok(i)), col = [0.85 0 0]; end
            plot(sc.Rmin(i), sc.v0(i), mk, 'Color', col, 'MarkerFaceColor', col, 'MarkerSize', 8);
        end
        plot(NaN, NaN, 'ko', 'MarkerFaceColor', 'k');  plot(NaN, NaN, 'ks', 'MarkerFaceColor', 'k');
        xline(150, 'k:');  yline(20, 'k:');  grid on;  xlabel('smallest curve radius (m)');  ylabel('speed (m/s)');
        title('Stress cases (green = success, red = failed); dotted = edge of training range');
        text(0.02, 0.04, 'circle = expert, square = network', 'Units', 'normalized');  set(gca, 'FontSize', fs);
        exportgraphics(f, fullfile(out, 'fig_stress.png'), 'Resolution', 200);  close(f);
    end
else
    fprintf('dsd_eval2.csv not found - skipped figure 2\n');
end

if isfile(fullfile('results', 'dsd_train.png')), copyfile(fullfile('results', 'dsd_train.png'), fullfile(out, 'fig_training.png')); end
fid = fopen(fullfile(out, 'tables.md'), 'w');  fprintf(fid, '%s\n', md{:});  fclose(fid);
fprintf('Done. Figures and tables are in %s\n', fullfile(here, out));
fprintf('%s\n', md{:});
end
