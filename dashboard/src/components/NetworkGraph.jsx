import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';

const NetworkGraph = ({ data, loading }) => {
  const svgRef = useRef(null);

  useEffect(() => {
    if (loading || !data || !svgRef.current) return;

    // Clear previous graph
    d3.select(svgRef.current).selectAll("*").remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.parentElement.clientHeight || 654;

    const svg = d3.select(svgRef.current)
      .attr("width", width)
      .attr("height", height);

    // Deep copy data to avoid mutating props
    const nodes = data.nodes.map(d => ({ ...d }));
    const links = data.links.map(d => ({ ...d }));

    const color = d3.scaleOrdinal()
      .domain([1, 2, 3, 4])
      .range(['#3B82F6', '#10B981', '#F59E0B', '#EF4444']);

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(30));

    // Links container
    const link = svg.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(255, 255, 255, 0.1)")
      .attr("stroke-width", d => Math.sqrt(d.value) * 1.5);

    // Nodes container
    const node = svg.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .call(drag(simulation));

    // Glow filter
    const defs = svg.append("defs");
    const filter = defs.append("filter")
      .attr("id", "glow");
    filter.append("feGaussianBlur")
      .attr("stdDeviation", "3.5")
      .attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    // Node circles
    node.append("circle")
      .attr("r", d => d.group === 1 ? 12 : (d.group === 4 ? 20 : 15))
      .attr("fill", d => color(d.group))
      .attr("stroke", "#111827")
      .attr("stroke-width", 2)
      .style("filter", "url(#glow)");

    // Tooltip implementation (simple title for now)
    node.append("title")
      .text(d => `${d.label}: ${d.id}`);

    // Node labels
    node.append("text")
      .attr("dx", 18)
      .attr("dy", ".35em")
      .text(d => d.id)
      .attr("fill", "#9CA3AF")
      .attr("font-size", "10px")
      .attr("font-family", "Inter, sans-serif")
      .attr("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

      node
        .attr("transform", d => `translate(${d.x},${d.y})`);
    });

    // Drag functions
    function drag(simulation) {
      function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
      }
      
      function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      }
      
      function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
      }
      
      return d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended);
    }

    return () => {
      simulation.stop();
    };
  }, [data, loading]);

  if (loading) {
     return (
        <div className="glassmorphism rounded-2xl p-6 h-full min-h-[654px] flex flex-col justify-center items-center">
          <div className="animate-pulse flex flex-col items-center gap-4">
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-primary/40"></div>
              <div className="w-16 h-1 bg-white/10 self-center"></div>
              <div className="w-12 h-12 rounded-full bg-danger/40"></div>
            </div>
            <div className="w-1 h-16 bg-white/10"></div>
            <div className="w-10 h-10 rounded-full bg-warning/40"></div>
          </div>
          <p className="text-gray-500 mt-6 text-sm font-medium">Analyzing Network...</p>
        </div>
      );
  }

  return (
    <div className="glassmorphism rounded-2xl p-4 h-full min-h-[654px] flex flex-col shadow-xl border border-white/10 relative overflow-hidden">
      <div className="flex justify-between items-center mb-2 px-2 z-10">
        <div>
          <h3 className="text-xl font-bold tracking-tight">Scam Syndicate Network</h3>
          <p className="text-sm text-gray-400">Force-directed graph of connections</p>
        </div>
        <div className="flex gap-4 text-xs">
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary"></span> Phone</div>
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-secondary"></span> UPI</div>
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-warning"></span> Agent</div>
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-danger"></span> Company</div>
        </div>
      </div>
      
      <div className="flex-1 w-full bg-card/30 rounded-xl relative border border-white/5 cursor-move">
        <svg ref={svgRef} className="w-full h-full" />
      </div>
    </div>
  );
};

export default NetworkGraph;
