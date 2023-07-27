/* eslint-disable no-undef */
/**
 * Back to home button
 */

// config map
let config = {
  minZoom: 7,
  maxZoom: 13,
};

// magnification with which the map will start
const zoom = 7.3;

// coordinates where the map will center
const lat = 38;
const lng = -79.5;

// coordinates for centering and zooming on state map
var nva = new L.Marker([39,-77]);
var seva = new L.Marker([38,-76]);
var swva = new L.Marker([38,-80]);
var cva = new L.Marker([38,-78]);


// calling map
var map = L.map('map', config).setView([lat,lng],zoom),
    geojsonLayer = new L.GeoJSON.AJAX("county.geojson", {style: style, onEachFeature: onEachFeature2}).addTo(map),
    clusterGroup = L.markerClusterGroup().addTo(map),
    qsoparty = L.featureGroup.subGroup(clusterGroup),
    nonqsoparty = L.featureGroup.subGroup(clusterGroup);

    window["qso-party"] = createRealtimeLayer( '/qso-party.json', qsoparty).addTo(map);
    window["non-qso-party"] = createRealtimeLayer( '/non-qso-party.json', nonqsoparty);

// Used to load and display tile layers on the map
// Most tile servers require attribution, which you can set under `Layer`
L.tileLayer('http://{s}.tile.osm.org/{z}/{x}/{y}.png').addTo(map);


/* Home Button */
const homeTemplate =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M32 18.451L16 6.031 0 18.451v-5.064L16 .967l16 12.42zM28 18v12h-8v-8h-8v8H4V18l12-9z" /></svg>';

// create custom button
const homeControl = L.Control.extend({
  // button position
  options: {
    position: "topleft",
  },

  // method
  onAdd: function (map) {
    // create button
    const btn = L.DomUtil.create("button");
    btn.title = "Show all VA";
    btn.innerHTML = homeTemplate;
    btn.className += "leaflet-bar back-to-home";

    return btn;
  },
});

const nvaControl = L.Control.extend({
  // button position
  options: {
    position: "topleft",
  },

  // method
  onAdd: function (map) {
    // create button
    const btn = L.DomUtil.create("button");
    btn.title = "Zoom N. Va";
    btn.innerHTML = "N Va";
    btn.className += "leaflet-bar to-nva";

    return btn;
  },
});

const cvaControl = L.Control.extend({
  // button position
  options: {
    position: "topleft",
  },

  // method
  onAdd: function (map) {
    // create button
    const btn = L.DomUtil.create("button");
    btn.title = "Zoom Cen. Va";
    btn.innerHTML = "C Va";
    btn.className += "leaflet-bar to-cva";

    return btn;
  },
});

const sevaControl = L.Control.extend({
  // button position
  options: {
    position: "topleft",
  },

  // method
  onAdd: function (map) {
    // create button
    const btn = L.DomUtil.create("button");
    btn.title = "Zoom S.E. Va";
    btn.innerHTML = "SE Va";
    btn.className += "leaflet-bar to-seva";

    return btn;
  },
});

const swvaControl = L.Control.extend({
  // button position
  options: {
    position: "topleft",
  },

  // method
  onAdd: function (map) {
    // create button
    const btn = L.DomUtil.create("button");
    btn.title = "Zoom S.W. Va";
    btn.innerHTML = "SW Va";
    btn.className += "leaflet-bar to-swva";

    return btn;
  },
});


// Maps Buttons 

// adding Home button to map control
map.addControl(new homeControl());

// adding NVa button to map control
map.addControl(new nvaControl());

// adding C Va button to map control
map.addControl(new cvaControl());

// adding SE Va button to map control
map.addControl(new sevaControl());

// adding SW Va button to map control
map.addControl(new swvaControl());

const buttonBackToHome = document.querySelector(".back-to-home");
const buttonNVa = document.querySelector(".to-nva");
const buttonCVa = document.querySelector(".to-cva");
const buttonSEVa = document.querySelector(".to-seva");
const buttonSWVa = document.querySelector(".to-swva");

buttonBackToHome.addEventListener("click", () => {
  map.flyTo([lat,lng], zoom);
});

buttonNVa.addEventListener("click", () => {
  map.flyTo([38.6,-78.25], 8.75);
});

buttonCVa.addEventListener("click", () => {
  map.flyTo([37.35,-78.5], 8.75);
});

buttonSEVa.addEventListener("click", () => {
  map.flyTo([37.35,-76.75], 8.75);
});

buttonSWVa.addEventListener("click", () => {
  map.flyTo([37.5,-81.8], 8.5);
});


/* Layers Checkboxes */
const layersContainer = document.querySelector(".layers");

const layersButton = "all stations";

function generateButton(name) {
  const id = name === layersButton ? "all-layers" : name; 

  const templateLayer = `<li class="layer-element"><label for="${id}"> <input type="checkbox" id="${id}" name="item" class="item" value="${name}" checked><span>${name}</span></label></li>`;

  layersContainer.insertAdjacentHTML("beforeend", templateLayer);
}

//generateButton(layersButton);

// add data to geoJSON layer and add to LayerGroup
// const arrayLayers = ["qso-party", "non-qso-party"];
const arrayLayers = ["qso-party"];

arrayLayers.map((json) => {
  generateButton(json);
/*
  fetchData(`../${json}.json`).then((data) => {
    window["layer_" + json] = L.geoJSON(data, geojsonOpts).addTo(map);
  });
*/
});

document.addEventListener("click", (e) => {
  const target = e.target;

  const itemInput = target.closest(".item");

  if (!itemInput) return;

  showHideLayer(target);
});

function showHideLayer(target) {
  if (target.id === "all-layers") {
    arrayLayers.map((json) => {
      checkedType(json, target.checked);
    });
  } else {
    checkedType(target.id, target.checked);
  }

  const checkedBoxes = document.querySelectorAll("input[name=item]:checked");

  document.querySelector("#all-layers").checked =
    checkedBoxes.length <= 2 ? false : true;

}

function checkedType(id, type) {
  map[type ? "addLayer" : "removeLayer"](window[id]);

  if ( !type ) {
    window[id].stop();
  } else {
    window[id].start();
  }
  
    map.flyTo([lat, lng], zoom);

  document.querySelector(`#${id}`).checked = type;
}


/* QP APRS Tracker - County Map Colors */
function getColor(d) {
    return d > 130  ? '#800026' :
           d > 120  ? '#BD0026' :
           d > 100  ? '#E31A1C' :
           d > 80   ? '#FC4E2A' :
           d > 60   ? '#FD8D3C' :
           d > 40   ? '#FEB24C' :
           d > 20   ? '#FED976' :
                      '#FFEDA0';
}

function getColor2(d) {
    return d > 130  ? '#0000FF' :
           d > 120  ? '#FF0000' :
           d > 100  ? '#00FF00' :
           d > 80   ? '#00FFFF' :
           d > 60   ? '#003399' :
           d > 40   ? '#FF33CC' :
           d > 20   ? '#EEEE33' :
           d > 0    ? '#888888' :
                      '#000000';
}

/* Fill County with Color */
function style(feature) {
    return {
        fillColor: getColor2(feature.id),
        weight: 2,
        opacity: 1,
        color: 'white',
        dashArray: '3',
        fillOpacity: 0.4
    };
}

/* Set up County Name */
function onEachFeature2(feature, layer) {
    // does this feature have a property called name?
    if (feature.properties && feature.properties.name) {
        layer.bindPopup('<h1>' + feature.properties.name + '</h1>');
    }
}

/* Create APRS Callsign Layer */
function createRealtimeLayer(url, container) {
    return L.realtime(url, {
        interval: 30 * 1000,
        getFeatureId: function(f) {
            return f.properties.scall;
        },
        cache: false,
        container: container,

        onEachFeature(f, l) {
            l.bindTooltip( f.properties.scall, {
              permanent: true,
              direction: 'auto'
            });
            l.bindPopup(function() {
                return '<h1>' + f.properties.call + '</h1>' +
                    '<p><h3>QP: Click road for county</h3>';
            });

            l.on("click", clickZoom);
        }
    });
}


// set center map
function clickZoom(e) {
  map.setView(e.target.getLatLng(), 13);

  setActive(e.sourceTarget.feature.properties.id);
}

window["qso-party"].on('click', function() {
    map.fitBounds(window["qso-party"].getBounds() );
});


window["non-qso-party"].on('click', function() {
    map.fitBounds(window["non-qso-party"].getBounds() );
});


/* Parse CSV file into Table form*/
var init;
const logFileText = async file => {
    const response = await fetch(file);
    const text = await response.text();
    all = text.split('\n');
        init = all.length;

        var arr=[];
        all.forEach(el => {
            el=el.split(',');
            arr.push(el);
        });

        createTable(arr);
}

/* Create the Table Call C&IC Age and Color Code according to Age */
function createTable(array) {
    var content = "<table>";
    array.forEach(function (row) {
        content += "<tr>";
        i = 0;
        row.forEach(function (cell) {
            if( i == 2) {
                content += "<td class=\"new\">" + cell + "</td>";
            } else if( i == 3) {
                content += "<td class=\"age\">" + cell + "</td>";
            } else {
               content += "<td>" + cell + "</td>";
            }
            i++;
        });
        content += "</tr>";
    });

    content += "</table>";

    document.getElementById("t1").innerHTML = content;

    var nw = document.getElementById("t1").getElementsByClassName("new");
    var age = document.getElementById("t1").getElementsByClassName("age");
    var tr = document.getElementById("t1").getElementsByTagName("tr");
    var td = document.getElementById("t1").getElementsByTagName("td");

    tr[0].style.font = "normal bold 20px arial,serif";
    tr[1].style.font = "normal bold 20px arial,serif";

    tr[0].style.backgroundColor = "cyan";
    tr[1].style.backgroundColor = "cyan";
    
    td[3].style.backgroundColor = "lightcyan";
    td[7].style.backgroundColor = "lightcyan";
    
    td[5].style.backgroundColor = "skyblue";
    td[6].style.backgroundColor = "skyblue";
    

    // Color code rows based on age in minutes of spot
    for ( i = 2; i < age.length; i++) {
        if( parseInt(nw[i].innerHTML) <= 30) {
            tr[i].style.font = "oblique bold 20px arial,serif";
        }

        if( parseInt(age[i].innerHTML) <= 60) {
            tr[i].style.backgroundColor = "lightgreen";
        } else if( parseInt(age[i].innerHTML) <= 120) {
            tr[i].style.backgroundColor = "yellow";
        } else if( parseInt(age[i].innerHTML) <= 180) {
            tr[i].style.backgroundColor = "pink";
        } else {
            tr[i].style.backgroundColor = "red";
        }
    }
}

/* Read latest APRS QSO Party spots file every 30 secs - Created by QP-APRS-Tracker.py */
var file = 'table.csv';
logFileText(file);
setInterval(async () => {
    await logFileText(file);
}, 30000);


/* Load LeftSide with static HTML content */
$(document).ready(function(){
    $('#content').load("aprs-new.html");
});
