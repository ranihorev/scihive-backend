var network;
var authors;
var base_data;
var all_nodes;
var all_edges;
var num_nodes = 0;



function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function setCookie(cname, value, days) {

    let max_age = '';
    if (days) {
        max_age = "; Max-Age=" + (days * 24 * 60 * 60)
    }
    let domain_text = '; Domain=' + window.location.hostname;
    document.cookie = cname + "=" + value + max_age + domain_text + "; path=/";
}


function removeCookie(cname) {
    setCookie(cname, '');
}

function focus_on_node(cur_authors) {
    var found = false;
    var focused = false;
    var found_authors = [];
    for( i=0; i < cur_authors.length; i++) {
        if (authors.indexOf(cur_authors[i].name) >= 0) {
            if (!focused) {
                network.focus(cur_authors[i].name, {animation: true, scale: 1});
                focused = true;
            }
            found_authors.push(cur_authors[i].name);
            found = true;
        }
    }
    if (found) {
        network.selectNodes(found_authors);
    } else {
        alert('Author/s not found');
    }
}

function toggle_spinner(to_show) {
    if (to_show) {
        $('body').addClass('dark');
        $('.spinner').show();
    } else {
        $('body').removeClass('dark');
        $('.spinner').hide();
    }
}


function changeCursor(newCursorStyle){
    var networkCanvas = document.getElementById("mynetwork").getElementsByTagName("canvas")[0]
    networkCanvas.style.cursor = newCursorStyle;
}

function update_network(nodes_to_show, stabilize = true) {
    toggle_spinner(true);
    num_nodes = nodes_to_show.length;
    network.setData({nodes: nodes_to_show, edges: all_edges});
    if (stabilize) {
        network.setOptions({physics: {enabled: true, solver: 'forceAtlas2Based', forceAtlas2Based: {avoidOverlap: 1}}});
        network.stabilize();

    }
    network.on('stabilizationIterationsDone', function() {
        setTimeout(function(){ network.fit(); }, 10);
        network.setOptions({physics: false});
        toggle_spinner(false);
    });
}

function draw_network(data) {
    all_nodes = new vis.DataSet(data['nodes']);
    num_nodes = all_nodes.length;
    // create an array with edges
    all_edges = new vis.DataSet(data['edges']);

    // create a network
    var container = document.getElementById('mynetwork');

    // provide the data in the vis format
    var graph_data = {
        nodes: all_nodes,
        edges: all_edges
    };
    var options = {
        layout: {
            improvedLayout: false
        },
        nodes: {
            shape: 'dot',
            scaling: {
                min: 7,
                max: 60,
                label: {
                    min: 14,
                    max: 25,
                    drawThreshold: 6,
                    maxVisible: 30
                }
            },
            font: {size: 14, face: 'Helvetica Neue, Helvetica, Arial'},
        },
        edges: {
            color: {
                color: 'rgba(50, 133, 236, 0.3)',
                highlight:'#c107fb',
            },
            smooth: false,

        },
        interaction: {
            navigationButtons: true,
            keyboard: false,
            hideEdgesOnDrag: true,
            tooltipDelay: 100
        },
        physics: false,
//        {
//            enabled: false,
//            stabilization: {
//              enabled: false,
//              iterations: 50,
//              updateInterval: 100,
//              onlyDynamicEdges: false,
//              fit: true
//            },
//            solver: 'forceAtlas2Based',
//            forceAtlas2Based: {
//                avoidOverlap: 1
//            }
//        }
    };

    // initialize your network!
    network = new vis.Network(container, graph_data, options);
    network.on("selectNode", function(params) {
        var sel_nodes = network.getSelectedNodes();
        $.get('/author_papers', {q: JSON.stringify(sel_nodes)}, function(res) {
            var papers = '';
            res.map(function(cur_p) {
                papers += `<div class='papers-list-item'><a href=${cur_p.url} target='_blank'>${cur_p.title}</a></div>`
            });

            $('#papers_list .author_name').text(`${sel_nodes[0]}`);
            $('#papers_list').show();
            $('#papers_list .content').html(papers);
        });
//      if (params.nodes.length == 1) {
//          if (network.isCluster(params.nodes[0]) == true) {
//              network.openCluster(params.nodes[0]);
//          }
//      }
    });

    network.on('hoverNode', function () {
        changeCursor('pointer');
    });
}

if (getCookie('welcome') !== '1') {
    $('#welcome').modal('show');
}
$('#welcome').on('hidden.bs.modal', function (e) {
    setCookie('welcome', '1', 30);
});

toggle_spinner(true);
$.getJSON("static/network_data.json", function (data) {
    console.log('Network graph was downloaded');
    base_data = data;
    draw_network(data);

    var input = document.getElementById("searchInput");
    authors = Array.from(data.nodes, function(d){ return(d.id) });
    network.on('afterDrawing', function() {
        toggle_spinner(false);
    });

});

$.get('/categories', function(res) {
    var options = '';
    $(res).each(function(index, item){ //loop through your elements
        if((item.key !== 'cs.CV') & (item.key !== 'cs.CL')){ //check the company
            options += `<a class="dropdown-item" href="#" value="${item.key}">${item.value}</a>`
        }
    });
    $('#categories_dropdown').append(options);
});

$("#categories_dropdown").on('click', '.dropdown-item', function(){
    $("#categories_button").text($(this).text());
    var val = $(this).attr('value');
    if (val === 'All') {
        var cur_nodes = all_nodes;
    }
    else {
        var cur_nodes = all_nodes.get({
          filter: function (item) {
            return item.fields.indexOf(val) >= 0;
          }
        });
    }
    num_nodes = cur_nodes.length;
    network.setData({nodes: cur_nodes, edges: all_edges});
});

$('#redraw').on('click', function(e) {
    if (num_nodes > 400) {
        alert('This feature is too slow for over 200 nodes');
        return;
    }
    toggle_spinner(true);
    var cur_nodes = network.body.data.nodes.getIds();
    for (i = 1; i < cur_nodes.length; i++) {
        network.moveNode(cur_nodes[i],0,0);
    };
    network.stabilize();

    network.on('stabilizationIterationsDone', function() {
        toggle_spinner(false);
        setTimeout(function(){ network.fit(); }, 10);

    });
});

var options = {
    url: function(phrase) {
        return "/autocomplete?q=" + phrase;
    },
    getValue: "name",
    list: {
		onClickEvent: function() {
		    var cur_s = $("#searchInput").getSelectedItemData();
		    console.log(cur_s);
		    if (cur_s.type === 'author') {
                focus_on_node([cur_s]);
		    } else { // paper
                focus_on_node(cur_s.authors);
		    }
		},
		maxNumberOfElements: 10,
		match: {
			enabled: true
		},
		requestDelay: 100
	},
	template: {
		type: "custom",
		method: function(value, item) {
		    var icon = (item.type === 'paper' ? 'newspaper' : 'user');
			return `<i class="fas fa-${icon}"></i> ${item.name}`
		}
	}

};
$("#searchInput").easyAutocomplete(options);

$('#searchInput').on('keypress', function(e) {
  if (e.which == 13) {
    var name = this.value.toLowerCase().split(' ').map((s) => s.charAt(0).toUpperCase() + s.substring(1)).join(' ');
    focus_on_node([{name: name}]);
    return false;    //<---- Add this line
  }
});

$('.collapse-expand').on('click', function(e) {
    $('#papers_list .content').toggle();
    $('.collapse-expand i').toggleClass('fa-minus');
    $('.collapse-expand i').toggleClass('fa-plus');
});

$('#focus').on('click', function(e) {
    var sel_nodes = network.getSelectedNodes();
    if (sel_nodes.length == 0) {
        alert('Please select a node to focus on');
        return;
    }
    var neighbours = network.getConnectedNodes(sel_nodes);
    var to_show_ids = neighbours.concat(sel_nodes);

    var nodes_to_show = all_nodes.get({
      filter: function (item) {
        return (to_show_ids.indexOf(item.id) >= 0);
      }
    });
    update_network(nodes_to_show);
    $('#expand').show();
});

$('#expand').on('click', function(e) {
    var sel_nodes = network.getSelectedNodes();
    var sel_node = sel_nodes[0]
    if (sel_nodes.length == 0) {
        alert('Please select a node to expand its neighbors');
        return;
    }

    // get edges of the selected node
    var sel_node_edges = all_edges.get({
      filter: function (item) {
        return (item.from == sel_node) | (item.to == sel_node)
      }
    });

    // Add current node neighbors to the currently displayed nodes
    var to_show_ids = network.body.nodeIndices;
    for( i=0; i < sel_node_edges.length; i++) {
        if (sel_node_edges[i].from !== sel_node) {
            to_show_ids.push(sel_node_edges[i].from);
        } else {
            to_show_ids.push(sel_node_edges[i].to);
        }
    }
    // Remove duplicates
    to_show_ids = Array.from(new Set(to_show_ids))

    // Filter dataset
    var nodes_to_show = all_nodes.get({
      filter: function (item) {
        return (to_show_ids.indexOf(item.id) >= 0);
      }
    });

    update_network(nodes_to_show);

});


$('#reset').on('click', function(e) {
    update_network(all_nodes, false);
});

$('#cluster').on('click', function(e) {
    var cur_node_ids = network.body.nodeIndices;
    num_components = Math.max.apply(Math, cur_node_ids.map(function(o) { return all_nodes.get(o).component; }))

    for (var i = 0; i <= 2; i++) {
          clusterOptionsByData = {
              joinCondition: function (childOptions) {
                  return childOptions.component == i; // the color is fully defined in the node.
              },
//              processProperties: function (clusterOptions, childNodes, childEdges) {
//                  var totalMass = 0;
//                  for (var i = 0; i < childNodes.length; i++) {
//                      totalMass += childNodes[i].mass;
//                  }
//                  clusterOptions.mass = totalMass;
//                  return clusterOptions;
//              },
//              clusterNodeProperties: {id: 'cluster:' + color, borderWidth: 3, shape: 'database', color:color, label:'color:' + color}
          };
          network.cluster(clusterOptionsByData);
      }
});
