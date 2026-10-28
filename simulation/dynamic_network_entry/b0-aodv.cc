// E2-011: original B0 application for the unmodified ns-3.46 stack.
// No source from prior project simulators is executed or overwritten.
#include "ns3/aodv-module.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/llc-snap-header.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/seq-ts-header.h"
#include "ns3/udp-header.h"
#include "ns3/wifi-module.h"

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

using namespace ns3;
namespace fs = std::filesystem;
static std::ofstream logFile;
static constexpr uint16_t PORT = 9000;
static constexpr uint32_t PAYLOAD = 512;

static void Prefix(const std::string& kind, uint32_t node)
{
    logFile << "{\"kind\":\"" << kind << "\",\"node\":" << node
            << ",\"t_s\":" << Simulator::Now().GetSeconds();
}

// Read-only instrumentation; SeqTs is in the actual UDP payload, not a free wire tag.
static int64_t ProbeSeq(Ptr<const Packet> packet, const Ipv4Header& header)
{
    if (header.GetProtocol() != 17) return -1;
    auto copy = packet->Copy();
    UdpHeader udp;
    if (copy->GetSize() < udp.GetSerializedSize()) return -1;
    copy->RemoveHeader(udp);
    if (udp.GetDestinationPort() != PORT) return -1;
    SeqTsHeader seq;
    if (copy->GetSize() < seq.GetSerializedSize()) return -1;
    copy->PeekHeader(seq);
    return seq.GetSeq();
}

static void IpTrace(uint32_t node, std::string kind, const Ipv4Header& header,
                    Ptr<const Packet> packet, uint32_t interface)
{
    const auto seq = ProbeSeq(packet, header);
    if (seq < 0) return;
    Prefix(kind, node);
    logFile << ",\"seq\":" << seq << ",\"ttl\":" << unsigned(header.GetTtl())
            << ",\"interface\":" << interface << ",\"ip_payload_bytes\":"
            << packet->GetSize() << "}\n";
}

static std::string FrameClass(Ptr<const Packet> packet)
{
    auto copy = packet->Copy();
    WifiMacHeader mac;
    if (copy->GetSize() < 10) return "unclassified";
    copy->RemoveHeader(mac);
    if (mac.IsCtl()) return "mac_control";
    if (mac.IsMgt()) return "management";
    if (!mac.IsData()) return "unclassified";
    LlcSnapHeader llc;
    if (copy->GetSize() < llc.GetSerializedSize()) return "unclassified_data";
    copy->RemoveHeader(llc);
    if (llc.GetType() == 0x0806) return "arp";
    if (llc.GetType() != 0x0800) return "other_data";
    Ipv4Header ip;
    if (copy->GetSize() < 20) return "unclassified_ip";
    copy->RemoveHeader(ip);
    if (ip.GetProtocol() != 17) return "other_ip";
    UdpHeader udp;
    if (copy->GetSize() < udp.GetSerializedSize()) return "unclassified_udp";
    copy->RemoveHeader(udp);
    if (udp.GetSourcePort() == 654 || udp.GetDestinationPort() == 654) return "aodv";
    if (udp.GetDestinationPort() == PORT) return "application";
    return "other_udp";
}

// ns-3.46 PhyTxBegin trace uses double watts (despite typed internal Watt_u APIs).
static void PhyTx(uint32_t node, Ptr<const Packet> packet, double watts)
{
    Prefix("phy_tx", node);
    logFile << ",\"packet_uid\":" << packet->GetUid()
            << ",\"frame_bytes\":" << packet->GetSize()
            << ",\"power_w\":" << watts
            << ",\"category\":\"" << FrameClass(packet) << "\"}\n";
}

static void PhyState(uint32_t node, Time start, Time duration, WifiPhyState state)
{
    // Record the actual PHY TX interval. State callbacks can report an interval
    // before/after its end; start_s, not callback order, is the join key.
    if (state != WifiPhyState::TX) return;
    Prefix("phy_tx_interval", node);
    logFile << ",\"start_s\":" << start.GetSeconds()
            << ",\"duration_s\":" << duration.GetSeconds() << "}\n";
}

static void Receive(Ptr<Socket> socket)
{
    Address sender;
    while (auto packet = socket->RecvFrom(sender))
    {
        const auto bytes = packet->GetSize();
        SeqTsHeader seq;
        NS_ABORT_MSG_IF(bytes < seq.GetSerializedSize(), "Malformed B0 probe");
        packet->RemoveHeader(seq);
        Prefix("app_rx", 2);
        logFile << ",\"seq\":" << seq.GetSeq()
                << ",\"bytes\":" << bytes << ",\"generated_s\":"
                << seq.GetTs().GetSeconds() << "}\n";
    }
}

static void Send(Ptr<Socket> socket, Ipv4Address destination, uint32_t seq)
{
    SeqTsHeader header;
    header.SetSeq(seq);
    auto packet = Create<Packet>(PAYLOAD - header.GetSerializedSize());
    packet->AddHeader(header);
    Prefix("app_generated", 0);
    logFile << ",\"seq\":" << seq << ",\"bytes\":" << PAYLOAD << "}\n";
    const auto result = socket->SendTo(packet, 0, InetSocketAddress(destination, PORT));
    Prefix("socket_result", 0);
    logFile << ",\"seq\":" << seq << ",\"return_bytes\":" << result << "}\n";
}

static void MoveLog(uint32_t node, Ptr<const MobilityModel> mobility)
{
    const auto p = mobility->GetPosition();
    Prefix("mobility", node);
    logFile << ",\"x_m\":" << p.x << ",\"y_m\":" << p.y << "}\n";
}

static void Mark(std::string name)
{
    Prefix("scenario_marker", 1);
    logFile << ",\"name\":\"" << name << "\",\"observer_only\":true}\n";
}

int main(int argc, char** argv)
{
    std::string output;
    std::string mode = "dynamic";
    uint32_t seed = 0;
    CommandLine cmd;
    cmd.AddValue("output", "New empty raw output directory", output);
    cmd.AddValue("mode", "dynamic or smoke", mode);
    cmd.AddValue("seed", "Dynamic 0/1; smoke 0", seed);
    cmd.Parse(argc, argv);
    if (output.empty() || (mode != "dynamic" && mode != "smoke") ||
        seed > 1 || (mode == "smoke" && seed != 0))
    {
        std::cerr << "Invalid bounded B0 configuration\n";
        return 2;
    }
    if (fs::exists(output) && !fs::is_empty(output))
    {
        std::cerr << "Refusing non-empty output\n";
        return 2;
    }
    fs::create_directories(output);
    logFile.open(fs::path(output) / "events.jsonl", std::ios::out);
    logFile << std::setprecision(17);
    NS_ABORT_MSG_IF(!logFile, "Cannot open event log");
    RngSeedManager::SetSeed(12345);
    RngSeedManager::SetRun(seed + 1);
    NodeContainer nodes;
    nodes.Create(3);

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::FriisPropagationLossModel", "Frequency", DoubleValue(5.18e9));
    channel.AddPropagationLoss("ns3::RangePropagationLossModel", "MaxRange", DoubleValue(125));
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("ChannelSettings", StringValue("{36, 20, BAND_5GHZ, 0}"));
    phy.Set("TxPowerStart", DoubleValue(16));
    phy.Set("TxPowerEnd", DoubleValue(16));
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211a);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager", "DataMode",
                                StringValue("OfdmRate6Mbps"), "ControlMode",
                                StringValue("OfdmRate6Mbps"));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    auto devices = wifi.Install(phy, mac, nodes);
    wifi.AssignStreams(devices, 10);

    MobilityHelper fixed;
    fixed.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    NodeContainer endpoints;
    endpoints.Add(nodes.Get(0));
    endpoints.Add(nodes.Get(2));
    fixed.Install(endpoints);
    nodes.Get(0)->GetObject<MobilityModel>()->SetPosition(Vector(0, 0, 0));
    nodes.Get(2)->GetObject<MobilityModel>()->SetPosition(Vector(mode == "smoke" ? 100 : 200, 0, 0));
    MobilityHelper moving;
    moving.SetMobilityModel("ns3::WaypointMobilityModel");
    moving.Install(nodes.Get(1));
    auto relay = nodes.Get(1)->GetObject<WaypointMobilityModel>();
    const double x = mode == "smoke" ? 50 : 100;
    for (const auto [t, y] : {std::pair<double, double>{0, 0}, {19, 0}, {21, 400},
                             {39, 400}, {41, 0}, {60, 0}})
    {
        relay->AddWaypoint(Waypoint(Seconds(t), Vector(x, mode == "smoke" ? 0 : y, 0)));
    }
    relay->TraceConnectWithoutContext("CourseChange", MakeBoundCallback(&MoveLog, uint32_t(1)));

    AodvHelper aodv;
    aodv.Set("MaxQueueTime", TimeValue(Seconds(3)));
    InternetStackHelper internet;
    internet.SetRoutingHelper(aodv);
    internet.Install(nodes);
    aodv.AssignStreams(nodes, 100);
    Ipv4AddressHelper addresses;
    addresses.SetBase("10.11.0.0", "255.255.255.0");
    auto interfaces = addresses.Assign(devices);

    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        auto ip = nodes.Get(i)->GetObject<Ipv4L3Protocol>();
        NS_ABORT_MSG_IF(!ip->TraceConnectWithoutContext("UnicastForward",
                         MakeBoundCallback(&IpTrace, i, std::string("ip_forward"))), "Missing forward trace");
        NS_ABORT_MSG_IF(!ip->TraceConnectWithoutContext("LocalDeliver",
                         MakeBoundCallback(&IpTrace, i, std::string("ip_deliver"))), "Missing deliver trace");
        auto device = DynamicCast<WifiNetDevice>(devices.Get(i));
        NS_ABORT_MSG_IF(!device->GetPhy()->TraceConnectWithoutContext("PhyTxBegin",
                         MakeBoundCallback(&PhyTx, i)), "Missing PHY TX trace");
        NS_ABORT_MSG_IF(!device->GetPhy()->GetState()->TraceConnectWithoutContext("State",
                         MakeBoundCallback(&PhyState, i)), "Missing PHY state trace");
    }
    phy.EnablePcap((fs::path(output) / "wifi").string(), devices, false);
    auto sink = Socket::CreateSocket(nodes.Get(2), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(sink->Bind(InetSocketAddress(Ipv4Address::GetAny(), PORT)) != 0, "Sink bind failed");
    sink->SetRecvCallback(MakeCallback(&Receive));
    auto source = Socket::CreateSocket(nodes.Get(0), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(source->Bind() != 0, "Source bind failed");
    for (uint32_t seq = 0; seq < 110; ++seq)
    {
        Simulator::Schedule(Seconds(5 + 0.5 * seq), &Send, source, interfaces.GetAddress(2), seq);
    }
    Simulator::Schedule(Seconds(22), &Mark, std::string("partition_check_start"));
    Simulator::Schedule(Seconds(38), &Mark, std::string("partition_check_end"));
    Simulator::Schedule(Seconds(42), &Mark, std::string("recovery_check_start"));
    Simulator::Stop(Seconds(60));
    Simulator::Run();
    Prefix("simulation_end", 0);
    logFile << ",\"mode\":\"" << mode << "\",\"seed\":" << seed << "}\n";
    source->Close();
    sink->Close();
    Simulator::Destroy();
    logFile.close();
    return 0;
}
