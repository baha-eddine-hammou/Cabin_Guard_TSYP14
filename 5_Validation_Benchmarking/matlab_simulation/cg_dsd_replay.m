function cg_dsd_replay(o, withNN)
% CG_DSD_REPLAY  Runs the SAME case twice in the closed-loop Simulink model (stop in lane / stop on shoulder)
%   and writes a bird's-eye video of the Driving Scenario road, both cars and the sensor view: results/dsd_replay.mp4
%   Example:  cg_dsd_replay                                   % default close-follower case on random road 3
%             cg_dsd_replay(struct('road','random','seed',7,'v0',17), true)    % learned driver
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, o = struct(); end
if nargin < 2, withNN = false; end
d = struct('road', 'random', 'seed', 3, 'gap0', 12, 'tau', 2.5, 'T', 14, 'accel', true, 'plot', false, 'quiet', true, 'nn', withNN);
f0 = fieldnames(o);  for k = 1:numel(f0), d.(f0{k}) = o.(f0{k}); end
d.nn = withNN;
R = cell(1, 2);
for k = 1:2
    d.shoulder = (k == 2);
    fprintf('simulating %s ...\n', ternary(k == 2, 'shoulder stop', 'stop in lane'));
    R{k} = cg_dsd_run(d);
end
info = R{1}.info;  lw = info.lw;  ta = info.opts.t_act;
% road edges and lane lines from the centre line
nx = -sin(info.hd);  ny = cos(info.hd);
offs = [-5.4 -1.8 1.8 5.4];
vn = fullfile('results', 'dsd_replay');
try, vw = VideoWriter(vn, 'MPEG-4'); catch, vw = VideoWriter(vn, 'Motion JPEG AVI'); end
vw.FrameRate = 10;  open(vw);
fig = figure('Visible', 'off', 'Position', [50 50 1280 640], 'Color', 'w');
step = 5;                                                  % 0.1 s per frame, one frame per 0.1 s, played in real time
n = min(numel(R{1}.t), numel(R{2}.t));
tit = {'Stop IN LANE', 'Stop on SHOULDER (authenticated MRM)'};
for i = 1:step:n
    clf(fig);
    for k = 1:2
        r = R{k};
        ax = subplot(3, 2, [k k + 2]);  hold(ax, 'on');
        for q = 1:4
            plot(ax, info.xd + offs(q) * nx(:), info.yd + offs(q) * ny(:), 'Color', ternary(q == 2 || q == 3, [0.6 0.6 0.6], [0.2 0.2 0.2]), 'LineStyle', ternary(q == 2 || q == 3, '--', '-'), 'LineWidth', 1.2);
        end
        % shoulder shading is implied by the outer solid line (lane 3 on the right of travel)
        ic = find(abs(r.fx) < 4.7 & abs(r.fy) < 1.9 & r.t > ta, 1);           % first contact (the scripted follower would drive through the ego)
        j = i;  if ~isempty(ic), j = min(i, ic); end
        xf = r.X(j) + cos(r.psi(j)) * r.fx(j) - sin(r.psi(j)) * r.fy(j);
        yf = r.Y(j) + sin(r.psi(j)) * r.fx(j) + cos(r.psi(j)) * r.fy(j);
        plot(ax, r.X(1:i), r.Y(1:i), 'b-', 'LineWidth', 1);
        drawCar(ax, r.X(i), r.Y(i), r.psi(i), [0 0.3 0.9]);
        coll = ~isempty(ic) && i >= ic;
        drawCar(ax, xf, yf, r.psi(j), ternary(coll, [0.9 0 0], [0.9 0.5 0]));
        if r.gap_radar(i) < 200 && r.gap_radar(i) > 0
            plot(ax, [r.X(i) r.X(i) - r.gap_radar(i) * cos(r.psi(i))], [r.Y(i) r.Y(i) - r.gap_radar(i) * sin(r.psi(i))], 'g-', 'LineWidth', 1.5);
        end
        axis(ax, 'equal');  xlim(ax, r.X(i) + [-40 40]);  ylim(ax, r.Y(i) + [-20 20]);  grid(ax, 'on');
        title(ax, sprintf('%s     t = %.1f s   v = %.1f m/s', tit{k}, r.t(i), r.vx(i)));
        if r.t(i) > ta, text(ax, 0.02, 0.95, 'MRM active', 'Units', 'normalized', 'Color', [0.8 0 0], 'FontWeight', 'bold'); end
        if coll, text(ax, 0.02, 0.80, sprintf('REAR-END COLLISION  %.1f m/s', info.vf(r.t(ic)) - r.vx(ic)), 'Units', 'normalized', 'Color', 'r', 'FontSize', 13, 'FontWeight', 'bold'); end
        % lower panel: speed and distance to the follower
        ax2 = subplot(3, 2, 4 + k);  hold(ax2, 'on');
        yyaxis(ax2, 'left');  plot(ax2, r.t(1:i), r.vx(1:i), 'b', 'LineWidth', 1.4);  ylim(ax2, [0 max(25, max(R{1}.vx))]);  ylabel(ax2, 'ego speed (m/s)');
        yyaxis(ax2, 'right');  plot(ax2, r.t(1:i), r.gap_true(1:i), 'm', 'LineWidth', 1.4);  plot(ax2, r.t(1:i), r.gap_radar(1:i), 'g.', 'MarkerSize', 3);  ylim(ax2, [0 60]);  ylabel(ax2, 'distance to follower (m)');
        yline(ax2, 4.7, 'r:');  xline(ax2, ta, 'r');  xlim(ax2, [0 d.T]);  grid(ax2, 'on');  xlabel(ax2, 't (s)');
    end
    sgtitle(fig, sprintf('CabinGuardDSD closed loop on a Driving Scenario road (%s, %s) - simulation', d.road, ternary(withNN, 'learned driver', 'MPC + PID driver')));
    drawnow;  writeVideo(vw, getframe(fig));
end
close(vw);  close(fig);
fprintf('Done. Video: %s\n', fullfile(here, [vn '.mp4']));
% optional: open the road in the Driving Scenario Designer app
try
    [sc, ~] = cg_dsd_scenario(d);  assignin('base', 'cg_scn_view', sc);
    fprintf('To look at the road in the app, type:  drivingScenarioDesigner(cg_scn_view)\n');
catch
end
end

function drawCar(ax, x, y, psi, col)
L = 4.7;  W = 1.9;
c = [-L/2 -W/2; L/2 -W/2; L/2 W/2; -L/2 W/2];
R = [cos(psi) -sin(psi); sin(psi) cos(psi)];
p = (R * c')' + [x y];
patch(ax, p(:,1), p(:,2), col, 'EdgeColor', 'k');
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
