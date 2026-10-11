function serviceValue(guide, name) {
  if (!guide || !guide.fields) return "";
  return guide.fields[name.toLowerCase()] || "";
}

function displayTime(minutes) {
  var hour = Math.floor(minutes / 60) % 24;
  var minute = minutes % 60;
  var suffix = hour >= 12 ? "PM" : "AM";
  var hour12 = hour % 12 || 12;
  return hour12 + ":" + String(minute).padStart(2, "0") + " " + suffix;
}

function rangeFromText(text) {
  var value = String(text || "");
  var dash = value.indexOf("-");
  if (dash < 0) {
    if (value.indexOf("24/7") >= 0) return [0, 1440];
    return null;
  }
  var before = value.slice(0, dash).match(/\d{3,4}$/);
  var after = value.slice(dash + 1).match(/^\d{3,4}/);
  if (!before || !after) return null;
  var start = Number(before[0]);
  var end = Number(after[0]);
  return [Math.floor(start / 100) * 60 + start % 100, Math.floor(end / 100) * 60 + end % 100];
}

function timelineRow(label, guideValue, now) {
  var range = rangeFromText(guideValue);
  var inRange = range && ((range[0] <= range[1] && now >= range[0] && now < range[1]) || (range[0] > range[1] && (now >= range[0] || now < range[1])));
  var trackClass = range ? (inRange ? " is-open" : " is-closed") : " is-unknown";
  var segment = "";
  if (range) {
    var start = range[0];
    var end = range[1];
    if (end <= start) end = 1440;
    segment = '<span class="availability-segment" style="left:' + (start / 14.4) + '%;width:' + ((end - start) / 14.4) + '%"></span>';
  }
  var state = range ? (inRange ? "Available now" : "Unavailable now") : "Hours not specified";
  return '<div class="availability-row"><strong>' + label + '</strong><div class="availability-track' + trackClass + '">' + segment + '</div><span class="availability-state">' + state + '</span></div>';
}

export function renderAvailabilityTimeline(options) {
  var root = options.container.closest(".availability-timeline");
  if (!options.guide || !options.localTime) { root.hidden = true; return; }
  var date = new Date(options.localTime + ":00");
  if (isNaN(date.getTime())) { root.hidden = true; return; }
  var now = date.getHours() * 60 + date.getMinutes();
  root.hidden = false;
  options.heading.textContent = "Today at " + options.guide.name;
  options.timeLabel.textContent = "Consultation time: " + displayTime(now);
  options.summary.textContent = "24-hour hospital-local availability timeline (00:00-24:00).";
  var axis = '<div class="availability-scale" aria-hidden="true">';
  for (var hour = 0; hour <= 24; hour += 3) axis += '<span style="left:' + (hour / 24 * 100) + '%">' + String(hour).padStart(2, "0") + ':00</span>';
  axis += '</div>';
  options.container.innerHTML = axis + timelineRow("CT perfusion", serviceValue(options.guide, "CT Perfusion"), now) + timelineRow("MRI", serviceValue(options.guide, "MRI"), now) + timelineRow("EEG", serviceValue(options.guide, "EEG"), now);
  var tracks = options.container.querySelectorAll(".availability-track");
  if (tracks.length > 0) {
    var marker = document.createElement("span");
    marker.className = "availability-now availability-now-global";
    marker.style.left = (tracks[0].offsetLeft + tracks[0].offsetWidth * now / 1440) + "px";
    marker.style.top = tracks[0].offsetTop + "px";
    marker.style.height = (tracks[tracks.length - 1].offsetTop + tracks[tracks.length - 1].offsetHeight - tracks[0].offsetTop) + "px";
    options.container.appendChild(marker);
  }
}
