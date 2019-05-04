var network;
var authors;
var base_data;
var all_nodes = [];
var all_edges = [];
var last_req_data;

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

function remove_dups(arr) {
    var seen = new Set();
    var unique_arr = [];
    for (var i = 0; i < arr.length; i++) {
        if (!(seen.has(arr[i].id))) {
            unique_arr.push(arr[i]);
            seen.add(arr[i].id);
        }
    }
    return unique_arr;
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

var physics_options = {
        enabled: true,
        stabilization: {
          enabled: true,
          iterations: 100,
        },
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
            avoidOverlap: 1
        }
    }

var network_options = {
    nodes: {
        shape: 'dot',
        size: 10,
        font: {size: 10, face: 'Helvetica Neue, Helvetica, Arial'},
    },
    edges: {
        color: {
            color: 'rgba(50, 133, 236, 0.3)',
            highlight:'#c107fb',
        },
    },
    groups: {
        references: {
            shape: 'icon',
            icon: { face: '"Font Awesome 5 Free"', code: '\uf1ea', size: 20, color: 'rgba(195, 0, 0, 0.7)'}
        },
        citations: {
            shape: 'icon',
            icon: { face: '"Font Awesome 5 Free"', code: '\uf1ea', size: 20, color: 'rgba(0, 153, 51, 0.7)'}
        },
        papers: {
            shape: 'icon',
            icon: { face: '"Font Awesome 5 Free"', code: '\uf1ea', size: 20, color: 'rgba(0, 124, 241, 0.7)'}
        },
        authors: {
            shape: 'icon',
            icon: { face: '"Font Awesome 5 Free"', code: '\uf007', size: 20, color: 'orange'}
        },
    },
    interaction: {
        navigationButtons: true,
        keyboard: false,
        hideEdgesOnDrag: false,
        tooltipDelay: 100
    },
    physics: physics_options
};



function handle_references(data, nodes, edges) {
    if (('references' in data) && (data.references)) {
        var references_edges = data.references.map(function(ref) {
            return {from: data.id, to: ref.arxivId || ref.paperId, arrows: 'to', color: {color: 'rgba(255, 39, 10, 0.3)'}, title: 'Reference'}
        });
        edges.push(...references_edges);
        nodes.push(...data.references.map(function(ref) {
            return {id: ref.arxivId || ref.paperId, label: ref.title.substring(0,30) + '...', title: ref.title, group: 'references'}
        }));
    }

}

function handle_citations(data, nodes, edges) {
    if (('citations' in data) && (data.citations)) {
        var citations_edges = data.citations.map(function(ref) {
            return {from: ref.arxivId || ref.paperId, to: data.id, arrows: 'to', color: {color: 'rgba(10, 245, 0, 0.5)'}, title: 'Citation'}
        });
        edges.push(...citations_edges);
        nodes.push(...data.citations.map(function(ref) {
            return {id: ref.arxivId || ref.paperId, label: ref.title.substring(0,30) + '...', title: ref.title, group: 'citations'}
        }));
    }
}

function handle_authors(data, nodes, edges) {
    if ('authors' in data) {
        var authors_edges = data.authors.map(function(a) {
            return {from: a.name, to: data.id, arrows: 'to', title: 'Author'}
        });
        edges.push(...authors_edges);
        nodes.push(...data.authors.map(function(a) {
            return {id: a.name, label: a.name, title: a.name, group: 'authors'}
        }));
    }
}

function handle_author_papers(data, nodes, edges, author_name) {
    nodes.push(...data.map(function(ref) {
        return {id: ref._id || ref.paperId, label: ref.title.substring(0,30) + '...', title: ref.title, group: 'papers'}
    }));
    var citations_edges = data.map(function(ref) {
        return {from: author_name, to: ref._id || ref.paperId, arrows: 'to', title: 'Author'}
    });
    edges.push(...citations_edges);
}

function get_paper_link(arxivId, paperId) {
    var link = arxivId ? `https://www.arxiv.org/abs/${arxivId}` : `https://www.semanticscholar.org/paper/${paperId}`;
    return link;
}

function get_author_link(name) {
    return `https://arxiv.org/search/?searchtype=author&query=${name}`;
}

function set_network_physics(status) {
    physics_options['enabled'] = status;
    network.setOptions({physics: physics_options});
}

function expand_paper(res, show_papers=true, show_authors=true) {
    var nodes = [];
    var edges = [];
    if (show_papers) {
        handle_references(res, nodes, edges);
        handle_citations(res, nodes, edges);
    }
    if (show_authors) {
        handle_authors(res, nodes, edges);
    }
    var cur_ids = network.body.nodeIndices;
    nodes = nodes.filter(n => cur_ids.indexOf(n.id) < 0);
    nodes = remove_dups(nodes);
    all_nodes.add(nodes);
    all_edges.add(edges);
};

function expand_author(node_id, res) {
    var nodes = [];
    var edges = [];
    handle_author_papers(res, nodes, edges, node_id);
    var cur_ids = network.body.nodeIndices;
    nodes = nodes.filter(n => cur_ids.indexOf(n.id) < 0);
    all_nodes.add(nodes);
    all_edges.add(edges);
}
function build_author_desc(node_id, res) {
    last_req_data = {'data': res, 'id': node_id, 'type': 'author'};
    $('#title_inner').attr('href', get_author_link(node_id));
    $('#title_inner').text(node_id);
    var papers = '';
    res.map(function(cur_p) {
        var ref_link = get_paper_link(cur_p._id, cur_p.paperId);
        papers += `<div class='papers-list-item'><a href=${ref_link} target='_blank'>${cur_p.title}</a> <a href='#' class="focus" data-target='${cur_p._id || cur_p.paperId}'><i class="fas fa-search-plus"></i></a></div>`
    });
    $('#author_content').html(papers);
    $('#author_content').show();
    $('#paper_menu').hide();
    $('#paper_content').hide();
    $('#node_data').show();

}
function build_paper_desc(res) {
    last_req_data = {'data': res, 'type': 'paper'};
    var link = get_paper_link(res._id, res.paperId);
    $('#title_inner').attr('href', link);
    $('#title_inner').text(res.title);
    if (res.references) {
        var ref_papers = '';
        res.references.map(function(cur_p) {
            var ref_link = get_paper_link(cur_p.arxivId, cur_p.paperId);
            ref_papers += `<div class='papers-list-item'><a href=${ref_link} target='_blank'>${cur_p.title}</a> <a href='#' class="focus" data-type='paper' data-target='${cur_p.arxivId || cur_p.paperId}'><i class="fas fa-search-plus"></i></a></div>`
        });
        $('#paper_references').html(ref_papers);
    } else {
        $('#paper_references').html('No references found');
    };
    if (res.citations) {
        var cit_papers = '';
        res.citations.map(function(cur_p) {
            var ref_link = get_paper_link(cur_p.arxivId, cur_p.paperId);
            cit_papers += `<div class='papers-list-item'><a href=${ref_link} target='_blank'>${cur_p.title}</a> <a href='#' class="focus" data-type='paper' data-target='${cur_p.arxivId || cur_p.paperId}'><i class="fas fa-search-plus"></i></a></div>`
        });
        $('#paper_citations').html(cit_papers);
    } else {
        $('#paper_citations').html('No citations found');
    }
    ;
    if (res.authors) {
        var paper_aut = '';
        res.authors.map(function(cur_a) {
            var ref_link = get_author_link(cur_a.name);
            paper_aut += `<div class='papers-list-item'><a href=${ref_link} target='_blank'>${cur_a.name}</a> <a href='#' class="focus" data-type='author' data-target='${cur_a.name}'><i class="fas fa-search-plus"></i></a></div>`
        });
        $('#paper_authors').html(paper_aut);
    } else {
        $('#paper_authors').html('No authors found');
    };
    $('#author_content').hide();
    $('#paper_menu').show();
    $('#paper_content').show();
    $('#node_data').show();
}

function init_network_events() {
    network.on('stabilized', function() {
        set_network_physics(false);
    });
    network.on("doubleClick", function() {
        var sel_node = network.body.data.nodes._data[network.getSelectedNodes()[0]];
        if (sel_node.group === 'authors') {
            $.get('/get_author', {name: sel_node.id}, function(res) {
                expand_author(sel_node.id, res);
            });
        } else {
            $.get('/get_paper', {id: sel_node.id}, function(res) {
                expand_paper(res);
            });
        }
    });
    network.on("selectNode", function(params) {
        var sel_node_id = network.getSelectedNodes()[0];
        var sel_node = network.body.data.nodes._data[sel_node_id];
        if (sel_node.group === 'authors') {
            $.get('/get_author', {name: sel_node_id}, function(res) {
                if (res) build_author_desc(sel_node_id, res);
            });
        } else {
            $.get('/get_paper', {id: sel_node_id}, function(res) {
                build_paper_desc(res);
            });
        }
    });
}

function draw_network(data, is_paper, author) {
    $('#filters-wrapper').removeClass('hidden');
    var edges = [];
    var nodes = [];
    if (is_paper) {
        nodes = [{id: data.id, label: data.title, title: data.title, group: 'papers'}];
        handle_references(data, nodes, edges);
        handle_citations(data, nodes, edges);
        handle_authors(data, nodes, edges);
        nodes = remove_dups(nodes);
    } else {
        nodes = [{id: author.name, label: author.name, title: author.name, group: 'authors'}];
        handle_author_papers(data, nodes, edges, author.name);
    }
    all_edges = new vis.DataSet(edges);
    all_nodes = new vis.DataSet(nodes);

    // create a network
    var container = document.getElementById('mynetwork');
    // provide the data in the vis format
    var graph_data = {
        nodes: all_nodes,
        edges: all_edges
    };

    // initialize your network!
    $('#mynetwork').addClass('network');
    $('#main').addClass('main-top');
    $('#main').removeClass('main-center');
    $('#main .main-section').addClass('inline-desktop');
    $('#logo').addClass('logo-top').removeClass('logo-center');
    $('#main-text').hide();
    network = new vis.Network(container, graph_data, network_options);
    set_network_physics(true);
    init_network_events();
}


function fetch_data_and_draw(cur_s) {
    cur_s['first'] = 1;
    if (cur_s.type == 'paper') {
        $.get('/get_paper', cur_s, function(res) {
            draw_network(res, true);
        });
    } else {
        $.get('/get_author', cur_s, function(res) {
            draw_network(res, false, cur_s);
        });
    }

}

function get_item_icon(item, with_name=true) {
    var icon = (item.type === 'paper' ? 'newspaper' : 'user');
    return `<i class="fas fa-${icon} item-icon"></i> ${with_name ? item.name : ''}`
}

var autocomplete_options = {
    url: function(phrase) {
        return "/autocomplete_2?q=" + phrase;
    },
    getValue: "name",
    list: {
		onClickEvent: function() {
		    var cur_s = $("#searchInput").getSelectedItemData();
            fetch_data_and_draw(cur_s);
		},
		onKeyEnterEvent: function() {
		    var cur_s = $("#searchInput").getSelectedItemData();
            fetch_data_and_draw(cur_s);
		},
		maxNumberOfElements: 15,
		requestDelay: 100
	},
	template: {
		type: "custom",
		method: function(value, item) {
		    return get_item_icon(item);
		}
	}

};
$("#searchInput").easyAutocomplete(autocomplete_options);

$('#searchInput').on('keypress', function(e) {
  if (e.which == 13) {
//    var name = this.value.toLowerCase().split(' ').map((s) => s.charAt(0).toUpperCase() + s.substring(1)).join(' ');
//    focus_on_node([{name: name}]);
    return false;    //<---- Add this line
  }
});

$('.collapse-expand').on('click', function(e) {
    $('#node_data .content-wrapper').toggle();
    $('.collapse-expand i').toggleClass('fa-minus');
    $('.collapse-expand i').toggleClass('fa-plus');
});

$('#redraw').on('click', function(e) {
    toggle_spinner(true);
//    network.setOptions({physics: physics_options})
    network.stabilize(100);

    network.on('stabilizationIterationsDone', function() {
        network.setOptions({physics: false});
        setTimeout(function(){ network.fit(); toggle_spinner(false);}, 10);

    });
});

function focus_on_node(node_id) {
    network.focus(node_id, {animation: true, scale: 1.3});
    network.selectNodes([node_id]);
}

$('body').on('click', '.focus', function(e) {
    e.preventDefault();
    var node_id = String($(this).data('target'));

    if (last_req_data.type == 'paper') {
        expand_paper(last_req_data.data, false, true);
    } else {
        expand_author(last_req_data.id, last_req_data.data);
    }
    focus_on_node(node_id);

});

$('.clear-input').on('click', function(e) {
    $('#searchInput').val('');
});

$('#page_info').on('click', function(e) {$('#welcome').modal('show');});

var popular_q_data;

$.get('/popular_queries', function (data) {
    var content = '';
    var max_len = 50;
    popular_q_data = data;
    data.map(function(x, idx) {
        content += `<div class='popular_q'>🔥 <a href='#' data-pos=${idx}>${x.name.substring(0,max_len)}${x.name.length > max_len ? '...' : ''}</a></div>`
    });
    $('#popular_queries_content').html(content);
})

$('body').on('click', '.popular_q a', function(e) {
    e.preventDefault();
    var cur_pos = parseInt($(this).data('pos'));
    var cur_q = popular_q_data[cur_pos];
    fetch_data_and_draw(cur_q);
    $('#searchInput').val(cur_q.name);
});
