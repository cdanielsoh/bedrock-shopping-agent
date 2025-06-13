import { users, getUserById, getUserDisplayName } from '../data/users';
import './UserSelector.css';

interface UserSelectorProps {
  selectedUserId: string;
  onUserIdChange: (userId: string) => void;
}

const UserSelector = ({ selectedUserId, onUserIdChange }: UserSelectorProps) => {
  const selectedUser = getUserById(selectedUserId);

  return (
    <div className="user-sidebar">
      <div className="sidebar-header">
        <h3>👤 User</h3>
      </div>
      
      <div className="user-dropdown-container">
        <select 
          value={selectedUserId} 
          onChange={(e) => onUserIdChange(e.target.value)}
          className="user-dropdown"
        >
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {getUserDisplayName(user)}
            </option>
          ))}
        </select>
      </div>
      
      {selectedUser && (
        <div className="selected-user-info">
          <div className="user-avatar-large">
            {selectedUser.gender === 'M' ? '👨' : '👩'}
          </div>
          
          <div className="user-details-compact">
            <div className="detail-compact">
              <span className="detail-icon">🎯</span>
              <div className="detail-text">
                <div className="detail-label">Persona</div>
                <div className="detail-value">{selectedUser.persona.replace(/_/g, ' ')}</div>
              </div>
            </div>
            
            <div className="detail-compact">
              <span className="detail-icon">💰</span>
              <div className="detail-text">
                <div className="detail-label">Discount</div>
                <div className="detail-value">{selectedUser.discount_persona.replace(/_/g, ' ')}</div>
              </div>
            </div>
            
            <div className="detail-compact">
              <span className="detail-icon">👤</span>
              <div className="detail-text">
                <div className="detail-label">Age</div>
                <div className="detail-value">{selectedUser.age} years</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserSelector;
