/* eslint-disable no-undef */

/* Parse CSV file into Table form*/
var init;
const logFileText = async file => {
//    const response = await fetch(file + "?_=" + Date.now());
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
//    }
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

/* Read APRS.TXT file every 30 secs - Created by QP-APRS-Tracker.py */
var file = 'table.csv';
logFileText(file);
setInterval(async () => {
    await logFileText(file);
}, 30000);

