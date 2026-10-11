function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, function (character) {
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character];
  });
}

function clock(minutes) {
  var hour = Math.floor(minutes / 60) % 24;
  var suffix = hour >= 12 ? "PM" : "AM";
  var hour12 = hour % 12 || 12;
  return hour12 + ":" + String(minutes % 60).padStart(2, "0") + " " + suffix;
}

function fieldValue(guide, name) {
  return guide && guide.fields && guide.fields[name.toLowerCase()] ? guide.fields[name.toLowerCase()] : "";
}

function windows(value) {
  var raw = String(value || "");
  if (!raw) return {kind:"unknown", ranges:[], text:"Not listed in this guide"};
  if (/24\s*\/\s*7/i.test(raw)) return {kind:"available", ranges:[[0, 1440]], text:raw};
  if (/\b(no|none|not available|unavailable)\b/i.test(raw)) return {kind:"unavailable", ranges:[], text:raw};
  var match = raw.match(/\b([01]?\d|2[0-4])([0-5]\d)\s*-\s*([01]?\d|2[0-4])([0-5]\d)\b/);
  if (!match) return {kind:"unknown", ranges:[], text:raw};
  var start = Number(match[1]) * 60 + Number(match[2]);
  var end = Number(match[3]) * 60 + Number(match[4]);
  if (end > start) return {kind:"available", ranges:[[start, end]], text:raw};
  return {kind:"available", ranges:[[start, 1440], [0, end]], text:raw};
}

function rowMarkup(label, value, now) {
  var schedule = windows(value);
  var segments = "";
  var state = "Hours not specified";
  var index;
  var isOpen = false;
  if (schedule.kind === "available") {
    for (index = 0; index < schedule.ranges.length; index += 1) {
      var range = schedule.ranges[index];
      var left = (range[0] / 1440 * 100).toFixed(3);
      var width = ((range[1] - range[0]) / 1440 * 100).toFixed(3);
      segments += '<span class="availability-segment" style="left:' + left + '%;width:' + width + '%"></span>';
    }
    state = "Unavailable now";
    for (index = 0; index < schedule.ranges.length; index += 1) {
      if (now >= schedule.ranges[index][0] && now < schedule.ranges[index][1]) { isOpen = true; state = "Available now - until " + clock(schedule.ranges[index][1] % 1440); }
    }
  } else if (schedule.kind === "unavailable") state = "Not available";
  var stateClass = schedule.kind === "available" ? (isOpen ? " is-open" : " is-closed") : (schedule.kind === "unknown" ? " is-unknown" : "");
  return '<div class="availability-row"><strong title="' + escapeHtml(schedule.text) + '">' + escapeHtml(label) + '</strong><div class="availability-track' + stateClass + '">' + segments + '</div><span class="availability-state">' + escapeHtml(state) + '</span></div>';
}

export function renderAvailabilityTimeline(options) {
  var root = options.container.closest(".availability-timeline");
  if (!options.guide || !options.localTime) { root.hidden = true; return; }
  var date = new Date(options.localTime + ":00");
  if (isNaN(date.getTime())) { root.hidden = true; return; }
  var now = date.getHours() * 60 + date.getMinutes();
  root.hidden = false;
  options.heading.textContent = "Today at " + options.guide.name;
  options.timeLabel.textContent = "Consultation time: " + clock(now);
  options.summary.textContent = "24-hour hospital-local availability timeline (00:00-24:00), derived from the selected hospital guide.";
  var scale = '<div class="availability-scale" aria-hidden="true">';
  for (var hour = 0; hour <= 24; hour += 3) scale += '<span style="left:' + (hour / 24 * 100).toFixed(3) + '%">' + String(hour).padStart(2, "0") + ":00</span>';
  scale += '</div>';
  options.container.innerHTML = scale + rowMarkup("CT perfusion", fieldValue(options.guide, "CT Perfusion"), now) + rowMarkup("MRI", fieldValue(options.guide, "MRI"), now) + rowMarkup("EEG", fieldValue(options.guide, "EEG"), now);
  var tracks = options.container.querySelectorAll(".availability-track");
  if (tracks.length) {
    var marker = document.createElement("span");
    marker.className = "availability-now availability-now-global";
    marker.style.left = (tracks[0].offsetLeft + tracks[0].offsetWidth * now / 1440) + "px";
    marker.style.top = tracks[0].offsetTop + "px";
    marker.style.height = (tracks[tracks.length - 1].offsetTop + tracks[tracks.length - 1].offsetHeight - tracks[0].offsetTop) + "px";
    options.container.appendChild(marker);
  }
}
