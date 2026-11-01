function p = cg_auto_prep(sc, egoID, o, info)
% CG_AUTO_PREP  Takes the start state of the ego out of ANY scenario (generated or exported from the Driving Scenario Designer)
%   and measures how much road there is to the right of the ego (distance from the ego to the right road edge),
%   by casting a ray against the road boundaries. This plays the role of a navigation-map attribute: "how far right can I go".
ego = sc.Actors([sc.Actors.ActorID] == egoID);
pos = ego.Position;  yaw = deg2rad(ego.Yaw);
p.x0 = pos(1) - sin(yaw) * o.e1_0;
p.y0 = pos(2) + cos(yaw) * o.e1_0;
p.psi0 = yaw + deg2rad(o.dpsi0);
v0 = o.v0;
if isempty(v0) && isfield(info, 'v0') && ~isempty(info.v0), v0 = info.v0; end
if isempty(v0), v0 = norm(ego.Velocity(1:2)); end
if v0 < 1
    v0 = 15;  fprintf('  (the ego has no start speed in the scenario: using 15 m/s. Set o.v0 to change.)\n');
end
p.v0 = v0;
p.lw0 = 3.6;  if isfield(info, 'lw') && ~isempty(info.lw), p.lw0 = info.lw; end
p.clear = NaN;  p.clear_src = '';
try
    p.clear = rightClear(sc, pos(1:2), yaw);
    p.clear_src = 'road boundaries (ray cast)';
catch e
    fprintf('  (road boundaries not available: %s)\n', strtok(e.message, newline));
end
if ~isfinite(p.clear)
    if isfield(info, 'clear_expected'), p.clear = info.clear_expected;  p.clear_src = 'scene description';
    else, p.clear = 0;  p.clear_src = 'unknown -> the car will not leave its lane'; end
end
if isfield(info, 'clear_expected') && abs(p.clear - info.clear_expected) > 1.0
    fprintf('  [note] road to the right: ray cast %.1f m, scene description %.1f m\n', p.clear, info.clear_expected);
end
end

function d = rightClear(sc, p, yaw)
nR = [sin(yaw) -cos(yaw)];
rb = roadBoundaries(sc);
if ~iscell(rb), rb = {rb}; end
d = inf;
for i = 1:numel(rb)
    B = rb{i};  if size(B, 1) < 2, continue, end
    a = B(1:end-1, 1:2);  b = B(2:end, 1:2);  e = b - a;
    % p + t*nR = a + u*e   ->   t*nR(1) - u*e1 = a1 - p1 ;  t*nR(2) - u*e2 = a2 - p2
    det_ = -nR(1) * e(:,2) + nR(2) * e(:,1);
    r1 = a(:,1) - p(1);  r2 = a(:,2) - p(2);
    ok = abs(det_) > 1e-9;
    t = nan(size(det_));  u = nan(size(det_));
    t(ok) = (-r1(ok) .* e(ok,2) + r2(ok) .* e(ok,1)) ./ det_(ok);
    u(ok) = (nR(1) * r2(ok) - nR(2) * r1(ok)) ./ det_(ok);
    hit = ok & t > 0.05 & u >= 0 & u <= 1;
    if any(hit), d = min(d, min(t(hit))); end
end
end
