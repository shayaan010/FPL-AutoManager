import EmptyState from "./EmptyState";

export default function TransferHistory({ transfers = [] }) {
  if (transfers.length === 0) {
    return (
      <EmptyState
        icon="history"
        title="No transfers yet"
        description="Approved transfers will show up here with the points they gained after each gameweek completes."
      />
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>GW</th>
          <th>Out</th>
          <th>In</th>
          <th>Sold</th>
          <th>Bought</th>
          <th>Points Gained</th>
          <th>Executed</th>
        </tr>
      </thead>
      <tbody>
        {transfers.map((t) => (
          <tr key={t.id}>
            <td>{t.gameweek}</td>
            <td>{t.player_out_name}</td>
            <td>{t.player_in_name}</td>
            <td>£{(t.selling_price / 10).toFixed(1)}m</td>
            <td>£{(t.purchase_price / 10).toFixed(1)}m</td>
            <td>{t.points_gained ?? "—"}</td>
            <td className="muted">{new Date(t.executed_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
