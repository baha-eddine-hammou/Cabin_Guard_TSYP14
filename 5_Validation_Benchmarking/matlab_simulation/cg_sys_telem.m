function delivered  = cg_sys_telem(t, ecall, cls, Pmax, cell_up, sms_up)
% EMERGENCY MESSAGE TRANSPORT (MEC): cellular retries at +0, +1, +3, +7 s (backoff 1,2,4),
% then SMS, then retry every 30 s. The manoeuvre never waits for it.
% cls and Pmax are the (anonymized) message content; the signature/encryption are
% unit-tested in Python, here only delivery timing is simulated.
persistent trig t0 done idx tn
if isempty(trig)
    trig = false;  t0 = 0;  done = false;  idx = 1;  tn = 0;
end
if ecall > 0.5 && ~trig
    trig = true;  t0 = t;  tn = t;  idx = 1;
end
if trig && ~done && t >= tn
    if idx <= 4
        ok = cell_up > 0.5;
    elseif idx == 5
        ok = sms_up > 0.5;
    else
        ok = (cell_up > 0.5) || (sms_up > 0.5);
    end
    if ok
        done = true;
    else
        idx = idx + 1;
        offs = [0 1 3 7 8];
        if idx <= 5
            tn = t0 + offs(idx);
        else
            tn = t + 30;
        end
    end
end
delivered = double(done);
end

